// Ejecuta el sketch REAL (simulador_sensores.ino) en el PC, sin placa: ver README.md de esta carpeta.
#include "Arduino.h"
#include "../simulador_sensores/simulador_sensores.ino"
int main() {
  setup();
  for (;;) { loop(); std::this_thread::sleep_for(std::chrono::milliseconds(5)); }
}
