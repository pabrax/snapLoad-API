
def notify(names, paths):
    if names:
        print("Descargas completas:")
        for n, p in zip(names, paths):
            print(f" - {n} → {p}")
    else:
        print("Falló la descarga :(")