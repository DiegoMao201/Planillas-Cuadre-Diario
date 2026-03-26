import hashlib
import getpass


def main() -> None:
    password = getpass.getpass("Ingrese la clave administrativa: ")
    confirm = getpass.getpass("Repita la clave administrativa: ")

    if password != confirm:
        raise SystemExit("Las claves no coinciden.")

    print(hashlib.sha256(password.encode()).hexdigest())


if __name__ == "__main__":
    main()