# Probar el sketch sin placa (en el PC)

`Arduino.h` es un reemplazo mínimo (Serial por stdout/stdin, `millis`, `random`) que permite compilar y ejecutar
**el mismo `simulador_sensores.ino`** con g++. Sirve para verificar la lógica y el formato JSON; **no prueba el
microcontrolador** (memoria, temporización real, puerto USB).

```bash
cd arduino/prueba_en_pc
g++ -std=c++17 -Wall -Wextra -I. -x c++ main.cpp -o sim
./sim                      # imprime una línea JSON por sector cada 2 s
# en otra terminal no hace falta nada: escriba en la misma consola un comando y Enter, p. ej.  hB  (helada en el sector B)
```
