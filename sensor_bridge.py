import os
import re
import time
import json
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from dotenv import load_dotenv
import serial
from serial.tools import list_ports

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SITE_URL = os.getenv("FERMENTECH_URL", "https://fermentech.onrender.com").rstrip("/")
SENSOR_TOKEN = os.getenv("FERMENTECH_SENSOR_TOKEN", "").strip()
SERIAL_PORT = os.getenv("ARDUINO_PORT", "").strip()
BAUD_RATE = int(os.getenv("ARDUINO_BAUD", "9600"))

# Aceita a linha exata impressa pelo sketch:
# Temperatura: 24.50 C
PADRAO_TEMPERATURA = re.compile(
    r"^\s*Temperatura:\s*(-?\d+(?:[.,]\d+)?)\s*C\s*$",
    re.IGNORECASE,
)


def mostrar_portas():
    portas = list(list_ports.comports())
    if not portas:
        print("Nenhuma porta serial encontrada. Conecte o Arduino por USB.")
        return
    print("Portas seriais encontradas:")
    for porta in portas:
        print(f"  {porta.device} - {porta.description}")


def enviar_temperatura(temperatura):
    url = f"{SITE_URL}/api/cocho/FT-001/temperatura"
    payload = json.dumps({"temperatura": temperatura}).encode("utf-8")
    requisicao = Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Sensor-Token": SENSOR_TOKEN,
        },
        method="POST",
    )

    try:
        with urlopen(requisicao, timeout=25) as resposta:
            corpo = resposta.read().decode("utf-8", errors="replace")
            print(f"FERMENTECH respondeu HTTP {resposta.status}: {corpo}")
            return True
    except HTTPError as erro:
        corpo = erro.read().decode("utf-8", errors="replace")
        print(f"Erro HTTP {erro.code}: {corpo}")
    except (URLError, TimeoutError) as erro:
        print(f"Falha de conexão com o FERMENTECH: {erro}")

    return False


def main():
    if not SENSOR_TOKEN:
        print("Configure FERMENTECH_SENSOR_TOKEN no .env antes de iniciar.")
        return

    if not SERIAL_PORT:
        mostrar_portas()
        print("Configure ARDUINO_PORT no .env (ex.: COM3).")
        return

    print(f"Conectando ao Arduino em {SERIAL_PORT}, {BAUD_RATE} baud...")
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as arduino:
            # Alguns Arduinos reiniciam quando a porta serial é aberta.
            time.sleep(2)
            print("Ponte ativa. Aguardando temperaturas reais...")
            while True:
                linha = arduino.readline().decode("utf-8", errors="ignore").strip()
                if not linha:
                    continue

                print(f"Arduino: {linha}")
                correspondencia = PADRAO_TEMPERATURA.match(linha)
                if not correspondencia:
                    continue

                temperatura = float(correspondencia.group(1).replace(",", "."))
                if temperatura == -127.0:
                    print("Leitura DS18B20 inválida (-127 °C); não enviada.")
                    continue
                if not -50 <= temperatura <= 125:
                    print("Leitura fora do intervalo do sensor; não enviada.")
                    continue

                enviar_temperatura(temperatura)

    except serial.SerialException as erro:
        print(f"Não foi possível abrir a porta serial: {erro}")
        mostrar_portas()
    except KeyboardInterrupt:
        print("\nPonte encerrada.")


if __name__ == "__main__":
    main()

