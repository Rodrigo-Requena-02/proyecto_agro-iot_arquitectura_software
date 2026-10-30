"""Fuentes de datos del gateway: Arduino por USB serial o generador por software."""
import json
import random
import time

from edge_common import RANGOS, log


class FuenteSerial:
    """Lee lineas del Arduino por USB. Si se desconecta el cable, reintenta abrir el puerto."""

    def __init__(self, puerto: str, baudios: int):
        self.puerto, self.baudios, self.ser = puerto, baudios, None

    def _abrir(self):
        import serial  # import tardio: --simular no necesita pyserial funcionando
        self.ser = serial.Serial(self.puerto, self.baudios, timeout=3)
        time.sleep(2)  # el Arduino UNO se reinicia al abrir el puerto
        self.ser.reset_input_buffer()
        log(f"Conectado a {self.puerto} @ {self.baudios} baudios")

    def lineas(self):
        import serial
        while True:
            try:
                if self.ser is None:
                    self._abrir()
                crudo = self.ser.readline()
                if crudo:
                    yield crudo.decode("utf-8", errors="replace")
            except (serial.SerialException, OSError) as e:
                log(f"Puerto serial no disponible ({e}). Reintentando en 3 s...")
                try:
                    if self.ser:
                        self.ser.close()
                except Exception:
                    pass
                self.ser = None
                time.sleep(3)

    def comando(self, letra: str) -> None:
        if self.ser:
            self.ser.write(letra.encode())


class FuenteSimulada:
    """Mismos datos que el sketch, generados por software (para probar sin Arduino)."""

    OBJ = {"n": (18.0, 60.0, 600.0), "h": (0.5, None, None), "s": (None, 15.0, None), "r": (None, None, 1000.0)}

    def __init__(self, intervalo: float):
        self.intervalo = intervalo
        self.v = {"t": 18.0, "h": 60.0, "r": 600.0, "p": 1.013}
        self.obj = {"t": 18.0, "h": 60.0, "r": 600.0, "p": 1.013}

    def comando(self, letra: str) -> None:
        if letra in self.OBJ:
            t, h, r = self.OBJ[letra]
            for k, x in (("t", t), ("h", h), ("r", r)):
                if x is not None:
                    self.obj[k] = x
            log(f"# escenario={letra}")

    def lineas(self):
        pasos = {"t": (0.15, 0.25), "h": (0.10, 0.8), "r": (0.20, 15), "p": (0.05, 0.002)}
        while True:
            for k, (frac, amp) in pasos.items():
                nuevo = self.v[k] + (self.obj[k] - self.v[k]) * frac + random.uniform(-amp, amp)
                lo, hi = RANGOS[k]
                self.v[k] = max(lo, min(hi, nuevo))
            yield json.dumps({"id": "SIM-A01", "t": round(self.v["t"], 1), "h": round(self.v["h"], 1),
                              "r": round(self.v["r"]), "p": round(self.v["p"], 3)})
            time.sleep(self.intervalo)
