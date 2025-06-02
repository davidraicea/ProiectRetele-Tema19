import os
import socket
import threading
import pickle
import time

SERVER_LIST = [
    ("127.0.0.1", 9000),
    ("127.0.0.1", 9001),
    ("127.0.0.1", 9002)
]

MY_HOST = "127.0.0.1"
MY_PORT = 0
ultima_incarcare_primita = None
vecini_directi = []
mesaje_procesate = set()


def executa_metoda_pe_server(server_ip, server_port, nume_clasa, nume_metoda, nr_fire, argumente=[]):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect((server_ip, server_port))
            cerere = ("EXECUTA_METODA", (nume_clasa, nume_metoda, nr_fire, argumente))
            s.sendall(pickle.dumps(cerere))
            raspuns = pickle.loads(s.recv(4096))

            if raspuns.get("status") == "clasa_lipsa":
                print(f"[CLIENT] Clasa {nume_clasa} nu a fost gasita pe server.")

                with open(f"{nume_clasa}.py", "rb") as f:
                    continut = f.read()

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                    s2.connect((server_ip, server_port))
                    s2.sendall(pickle.dumps(("TRIMITE_CLASA", (nume_clasa, continut))))
                    resp = pickle.loads(s2.recv(4096))
                    print(f"[CLIENT] Raspuns server dupa trimitere clasa: {resp}")

                time.sleep(0.2)  
                return executa_metoda_pe_server(server_ip, server_port, nume_clasa, nume_metoda, nr_fire, argumente)


            elif raspuns.get("status") == "ok":
                return raspuns.get("rezultate", [])
    except Exception as e:
        print(f"[CLIENT] Eroare la executia metodei: {e}")

def alege_server_minim_incarcat():
    min_incarcare = float("inf")
    server_ales = None

    for ip, port in SERVER_LIST:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, port))
                s.sendall(pickle.dumps(("GET_INCARCARE",)))
                raspuns = pickle.loads(s.recv(4096))
                incarcare = raspuns.get("incarcare", float("inf"))
                print(f"[CLIENT] Incarcare pentru {ip}:{port} = {incarcare}")

                if incarcare < min_incarcare:
                    min_incarcare = incarcare
                    server_ales = (ip, port)

        except Exception as e:
            print(f"[CLIENT] Eroare la interogarea serverului cu portul: {port}")

    if server_ales:
        print(f"[CLIENT] Server selectat: {server_ales[0]}:{server_ales[1]} (load minim: {min_incarcare})")
    else:
        print("[CLIENT] Nu s-a putut selecta niciun server.")

    return server_ales
def gestioneaza_cerere_client(conn, addr):
    try:
        data = pickle.loads(conn.recv(4096))

        if data[0] == "NOTIFICARE_CLIENT_NOU":
            ip_nou, port_nou = data[1]
            print(f"[CLIENT-SERVER] Ai un nou vecin: {ip_nou}:{port_nou}")

            if (ip_nou, port_nou) not in vecini_directi and (ip_nou, port_nou) != (MY_HOST, MY_PORT):
                vecini_directi.append((ip_nou, port_nou))

                for ip, port in vecini_directi:
                    if (ip, port) != (ip_nou, port_nou):
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                                s.connect((ip, port))
                                s.sendall(pickle.dumps(("NOTIFICARE_CLIENT_NOU", (ip_nou, port_nou))))
                        except Exception as e:
                            print(f"[CLIENT-SERVER] Eroare propagare catre {ip}:{port} - {e}")

        elif data[0] == "UPDATE_INCARCARE":
            valoare = data[1]
            sursa = data[2] if len(data) > 2 else None
            mesaj_id = data[3] if len(data) > 3 else None

            if mesaj_id in mesaje_procesate:
                return
            mesaje_procesate.add(mesaj_id)
            global ultima_incarcare_primita

            print(f"[CLIENT] Primit actualizare load: {valoare}")
            ultima_incarcare_primita = valoare

            for ip, port in vecini_directi:
                if (ip, port) == sursa:
                    continue
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((ip, port))
                        s.sendall(pickle.dumps(("UPDATE_INCARCARE", valoare, (MY_HOST, MY_PORT), mesaj_id)))
                        print(f"[CLIENT] Propagare load catre {ip}:{port}")
                except Exception as e:
                    print(f"[CLIENT] Propagare eroare catre {ip}:{port} - {e}")


        elif data[0] == "CLIENT_DECONECTAT":
            ip_out, port_out = data[1]
            sursa = data[2] if len(data) > 2 else None

            print(f"[CLIENT] Clientul {ip_out}:{port_out} s-a deconectat")

            if (ip_out, port_out) in vecini_directi:
                vecini_directi.remove((ip_out, port_out))
                print(f"[CLIENT] Eliminat din vecini: {ip_out}:{port_out}")

            for ip, port in vecini_directi[:]:
                if (ip, port) != (ip_out, port_out) and (ip, port) != sursa:
                    try:
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                            s.connect((ip, port))
                            s.sendall(pickle.dumps(("CLIENT_DECONECTAT", (ip_out, port_out), (MY_HOST, MY_PORT))))
                            print(f"[CLIENT] Propagare deconectare catre {ip}:{port}")
                    except Exception as e:
                        print(f"[CLIENT] Vecin inactiv {ip}:{port} - {e}")
                        if (ip, port) in vecini_directi:
                            vecini_directi.remove((ip, port))

    except Exception as e:
        print(f"[CLIENT-SERVER] Eroare la primire cerere - {e}")
    finally:
        conn.close()


def start_client_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((MY_HOST, 0))
    s.listen()
    global MY_PORT
    MY_PORT = s.getsockname()[1]
    print(f"[CLIENT-SERVER] Ascult pe portul local {MY_PORT}")

    def handler():
        while True:
            conn, addr = s.accept()
            threading.Thread(target=gestioneaza_cerere_client, args=(conn, addr), daemon=True).start()

    threading.Thread(target=handler, daemon=True).start()

def conecteaza_la_servere():
    global vecini_directi
    for ip, port in SERVER_LIST:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, port))
                print(f"[CLIENT] Conectat la serverul {ip}:{port}")
                s.sendall(pickle.dumps(("CONEXIUNE_CLIENT", (MY_HOST, MY_PORT))))
                raspuns = pickle.loads(s.recv(4096))
                print(f"[CLIENT] Conexiune acceptata. Vecini existenti: {raspuns.get('vecini', [])}")

                for ip_v, port_v in raspuns.get("vecini", []):
                    if (ip_v, port_v) != (MY_HOST, MY_PORT) and (ip_v, port_v) not in vecini_directi:
                        vecini_directi.append((ip_v, port_v))
                        try:
                            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                                s2.connect((ip_v, port_v))
                                s2.sendall(pickle.dumps(("NOTIFICARE_CLIENT_NOU", (MY_HOST, MY_PORT))))
                                print(f"[CLIENT] Notificat vecin {ip_v}:{port_v}")
                        except Exception as e:
                            print(f"[CLIENT] Eroare notificare catre vecin {ip_v}:{port_v} - {e}")
                break
        except Exception as e:
            print(f"[CLIENT] Esuat la conectarea cu {ip}:{port}")

def meniu_client():
    while True:
        print("\n====== MENIU CLIENT ======")
        print("1. Afișează vecini direcți")
        print("2. Execută metodă pe server")
        print("3. Ieșire")
        print("===========================")
        opt = input("Alege opțiune: ")

        if opt == "1":
            if vecini_directi:
                print(f"[INFO] Vecini directi ({len(vecini_directi)}):")
                for ip, port in vecini_directi:
                    print(f"- {ip}:{port}")
            else:
                print("[INFO] Nu există vecini directi conectati.")
        elif opt == "2":
            server_ales = alege_server_minim_incarcat()
            if server_ales:
                ip, port = server_ales
                rezultate = executa_metoda_pe_server(ip, port, "Procesator", "proceseaza", 5, [5, 4, 3, 6, 7])
                print(f"[CLIENT] Rezultate obținute: {rezultate}")
        elif opt == "3":
            print("[CLIENT] Inchidere client...")
            for ip, port in SERVER_LIST:
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((ip, port))
                        s.sendall(pickle.dumps(("CLIENT_DECONECTARE", (MY_HOST, MY_PORT))))
                except:
                    continue
            time.sleep(0.5)
            os._exit(0)
        else:
            print("[CLIENT] Optiunea nu exista.")

if __name__ == "__main__":
    start_client_server()
    conecteaza_la_servere()
    time.sleep(1)
    meniu_client()
