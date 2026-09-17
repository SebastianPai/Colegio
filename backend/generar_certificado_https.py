"""Genera (o renueva) el certificado HTTPS local para IETABA.

Por que hace falta: el navegador solo permite usar la camara
(`getUserMedia`, que usa el escaner de documentos) en un "contexto
seguro" — HTTPS, o `localhost`. Esta app corre sin internet en la red del
colegio, así que no hay forma de conseguir un certificado público
(Let's Encrypt exige un dominio real y validación por internet). La
solución es un HTTPS "casero": una Autoridad Certificadora (CA) propia que
se instala UNA VEZ en cada celular, y un certificado de servidor firmado
por ella para la IP de este equipo.

Uso:
    python generar_certificado_https.py [ip_o_nombre_extra ...]

Volver a ejecutar cada vez que cambie la IP de este equipo (por ejemplo si
el router se la reasigna). La CA no cambia — los celulares que ya la
instalaron no tienen que hacer nada de nuevo — solo se renueva el
certificado del servidor con la IP actual.

Recomendado: pedirle al encargado de la red del colegio una reserva DHCP
(IP fija) para este equipo, para no tener que repetir este paso.
"""

import datetime as dt
import ipaddress
import socket
import sys
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

CARPETA_CERTS = Path(__file__).resolve().parent / "certs"
CA_KEY = CARPETA_CERTS / "ca-key.pem"
CA_CERT = CARPETA_CERTS / "ca-cert.pem"
SERVER_KEY = CARPETA_CERTS / "server-key.pem"
SERVER_CERT = CARPETA_CERTS / "server-cert.pem"
# Copia pública de la CA sin la llave privada: se sirve desde /static/ca.crt
# para que los celulares puedan descargarla e instalarla directamente.
CA_CERT_PUBLICO = Path(__file__).resolve().parent.parent / "frontend" / "static" / "ca.crt"


def detectar_ip_lan() -> str:
    """La IP con la que este equipo se ve desde la red local. No necesita
    internet real: solo abre un socket UDP hacia una IP externa para que
    el sistema operativo elija la interfaz de salida (no se envía nada)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def generar_clave():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def guardar_clave(clave, ruta: Path):
    ruta.write_bytes(
        clave.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def obtener_o_crear_ca():
    if CA_KEY.exists() and CA_CERT.exists():
        clave = serialization.load_pem_private_key(CA_KEY.read_bytes(), password=None)
        cert = x509.load_pem_x509_certificate(CA_CERT.read_bytes())
        print(f"Reutilizando la CA existente ({CA_CERT.name}) — los celulares que ya la instalaron siguen sirviendo.")
        return clave, cert

    print("No hay CA todavía — creando 'IETABA Local CA' (una sola vez)...")
    clave = generar_clave()
    nombre = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, "IETABA Local CA"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "IETABA"),
        ]
    )
    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(nombre)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - dt.timedelta(days=1))
        .not_valid_after(ahora + dt.timedelta(days=3650))  # 10 años: es solo para uso interno del colegio
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(clave.public_key()), critical=False)
        .sign(clave, hashes.SHA256())
    )
    CARPETA_CERTS.mkdir(exist_ok=True)
    guardar_clave(clave, CA_KEY)
    CA_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return clave, cert


def generar_certificado_servidor(ca_clave, ca_cert, extras: list[str]):
    ip_principal = detectar_ip_lan()
    valores = {ip_principal, "127.0.0.1", *extras}

    clave = generar_clave()
    nombre = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip_principal)])
    alternativos = [x509.DNSName("localhost")]
    for valor in sorted(valores):
        try:
            alternativos.append(x509.IPAddress(ipaddress.ip_address(valor)))
        except ValueError:
            alternativos.append(x509.DNSName(valor))  # por si pasan un hostname en vez de una IP

    ahora = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(nombre)
        .issuer_name(ca_cert.subject)
        .public_key(clave.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ahora - dt.timedelta(days=1))
        .not_valid_after(ahora + dt.timedelta(days=825))  # límite que aceptan los navegadores modernos
        .add_extension(x509.SubjectAlternativeName(alternativos), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(ca_clave, hashes.SHA256())
    )
    guardar_clave(clave, SERVER_KEY)
    SERVER_CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return ip_principal, sorted(valores)


def main():
    ca_clave, ca_cert = obtener_o_crear_ca()
    ip_principal, ips = generar_certificado_servidor(ca_clave, ca_cert, sys.argv[1:])

    CA_CERT_PUBLICO.parent.mkdir(parents=True, exist_ok=True)
    CA_CERT_PUBLICO.write_bytes(CA_CERT.read_bytes())

    print()
    print(f"Certificado de servidor listo para: {', '.join(ips)}")
    print(f"CA pública copiada a {CA_CERT_PUBLICO} (queda disponible en /static/ca.crt).")
    print()
    print("Siguiente paso:")
    print("  1. Iniciar el servidor HTTPS:  .\\iniciar_https.ps1")
    print(f"  2. Desde el celular, entrar a http://{ip_principal}:8000/static/ca.crt")
    print("     e instalar el certificado (ver instrucciones en el README).")
    print(f"  3. Usar el escáner desde  https://{ip_principal}:8443")


if __name__ == "__main__":
    main()
