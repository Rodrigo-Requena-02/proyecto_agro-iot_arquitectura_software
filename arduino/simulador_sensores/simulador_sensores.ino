/*
 * Simulador de sensores agricolas - Arduino UNO (conexion USB / cable serial)
 *
 * No requiere ningun sensor conectado. Simula TRES sectores (A, B y C) con datos
 * DISTINTOS: cada sector tiene su propio perfil (clima base) y su propia evolucion
 * aleatoria independiente. Cada INTERVALO_MS envia una linea JSON por sector:
 *
 *   {"id":"UNO-A01","s":"A","t":22.1,"h":65.3,"r":452,"p":1.003}
 *   {"id":"UNO-B01","s":"B","t":24.2,"h":79.8,"r":248,"p":2.510}
 *   {"id":"UNO-C01","s":"C","t":14.0,"h":41.7,"r":748,"p":1.795}
 *
 *   t = temperatura (C)   h = humedad de suelo (%)   r = radiacion (W/m2)   p = presion (bar)
 *
 * Perfiles base (condicion "normal", no disparan alertas):
 *   A invernadero : calido y humedo, poca radiacion
 *   B hidroponico : muy humedo, poca radiacion, presion de linea alta (bomba)
 *   C frutal      : fresco, suelo mas seco, mucha radiacion (al aire libre)
 *
 * Comandos (una linea por serial, terminada en salto de linea; los envia el gateway):
 *   <escenario>        aplica a TODOS los sectores      ej.  h
 *   <escenario><A|B|C> aplica solo a ese sector          ej.  hB
 *   Escenarios:  n = normal   h = helada (~0.5 C)   s = sequia (~15 %)   r = radiacion alta (~1000 W/m2)
 *
 * Las lineas que empiezan con '#' son mensajes informativos y el gateway las ignora.
 * Cargar con Arduino IDE: Herramientas > Placa > Arduino UNO, elegir el puerto, Subir.
 */

const unsigned long INTERVALO_MS = 2000;
const long BAUDIOS = 9600;
const byte N = 3;  // sectores

const char LETRA[N] = {'A', 'B', 'C'};
const char* const ID[N] = {"UNO-A01", "UNO-B01", "UNO-C01"};

// Perfil normal de cada sector: temperatura, humedad, radiacion, presion
const float BASE_T[N] = {22.0, 24.0, 14.0};
const float BASE_H[N] = {65.0, 80.0, 42.0};
const float BASE_R[N] = {450.0, 250.0, 750.0};
const float BASE_P[N] = {1.000, 2.500, 1.800};

// Estado actual y objetivo de cada sector
float t[N], h[N], r[N], p[N];
float oT[N], oH[N], oR[N], oP[N];
unsigned long ultimoEnvio = 0;
char comando[4];
byte largoCmd = 0;

// Numero aleatorio decimal en [-amp, +amp]
float ruido(float amp) {
  return ((float)random(-1000, 1001) / 1000.0) * amp;
}

// Mueve 'actual' hacia 'objetivo' una fraccion del camino y agrega ruido
float acercar(float actual, float objetivo, float fraccion, float amp) {
  return actual + (objetivo - actual) * fraccion + ruido(amp);
}

float limitar(float v, float minimo, float maximo) {
  if (v < minimo) return minimo;
  if (v > maximo) return maximo;
  return v;
}

void escenario(byte i, char c) {
  switch (c) {
    case 'n': oT[i] = BASE_T[i]; oH[i] = BASE_H[i]; oR[i] = BASE_R[i]; break;
    case 'h': oT[i] = 0.5;    break;
    case 's': oH[i] = 15.0;   break;
    case 'r': oR[i] = 1000.0; break;
  }
}

// Interpreta "<escenario>" o "<escenario><sector>"
void aplicarComando(const char* cmd, byte largo) {
  if (largo == 0) return;
  char esc = cmd[0];
  if (esc != 'n' && esc != 'h' && esc != 's' && esc != 'r') return;
  if (largo >= 2) {
    for (byte i = 0; i < N; i++) {
      if (cmd[1] == LETRA[i]) {
        escenario(i, esc);
        Serial.print(F("# escenario=")); Serial.print(esc);
        Serial.print(F(" sector=")); Serial.println(LETRA[i]);
        return;
      }
    }
    return;  // sector desconocido
  }
  for (byte i = 0; i < N; i++) escenario(i, esc);
  Serial.print(F("# escenario=")); Serial.print(esc); Serial.println(F(" sector=TODOS"));
}

void leerComandos() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      aplicarComando(comando, largoCmd);
      largoCmd = 0;
    } else if (largoCmd < sizeof(comando) - 1) {
      comando[largoCmd++] = c;
    }
  }
}

void setup() {
  Serial.begin(BAUDIOS);
  randomSeed(analogRead(A0));  // pin flotante = semilla distinta en cada encendido
  for (byte i = 0; i < N; i++) {
    // Arranque con un pequeno desfase para que los sectores no sean identicos desde el inicio
    t[i] = oT[i] = BASE_T[i] + ruido(1.0);
    h[i] = oH[i] = BASE_H[i] + ruido(4.0);
    r[i] = oR[i] = BASE_R[i] + ruido(40.0);
    p[i] = oP[i] = BASE_P[i] + ruido(0.05);
  }
  Serial.println(F("# simulador listo: sectores A, B y C"));
}

void loop() {
  leerComandos();

  if (millis() - ultimoEnvio >= INTERVALO_MS) {
    ultimoEnvio = millis();

    for (byte i = 0; i < N; i++) {
      t[i] = limitar(acercar(t[i], oT[i], 0.35, 0.25), -40, 60);
      h[i] = limitar(acercar(h[i], oH[i], 0.25, 0.8),  0, 100);
      r[i] = limitar(acercar(r[i], oR[i], 0.20, 15),   0, 1500);
      p[i] = limitar(acercar(p[i], oP[i], 0.05, 0.002), 0, 10);

      Serial.print(F("{\"id\":\""));  Serial.print(ID[i]);
      Serial.print(F("\",\"s\":\""));  Serial.print(LETRA[i]);
      Serial.print(F("\",\"t\":"));    Serial.print(t[i], 1);
      Serial.print(F(",\"h\":"));      Serial.print(h[i], 1);
      Serial.print(F(",\"r\":"));      Serial.print(r[i], 0);
      Serial.print(F(",\"p\":"));      Serial.print(p[i], 3);
      Serial.println(F("}"));
    }
  }
}
