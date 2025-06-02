import socket
import threading
import pickle
import importlib.util
import os
import uuid
import sys

MY_HOST = "127.0.0.1"
MY_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 9000  

clienti = []
incarcare_server = 0
clase_path = "clase"
os.makedirs(clase_path, exist_ok=True)

def incarca_clasa_din_fisier(nume_clasa):
    try:
        fisier = os.path.join(clase_path, f"{nume_clasa}.py")
        if not os.path.exists(fisier):
            print(f"[SERVER] Fisierul clasei {fisier} nu exista.")
            return None

        spec = importlib.util.spec_from_file_location(nume_clasa, fisier)
        if spec is None or spec.loader is None:
            print(f"[SERVER] Eroare la incarcare spec pentru {fisier}")
            return None

        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        return getattr(modul, nume_clasa)
    except Exception as e:
        print(f"[SERVER] Eroare la incarcarea clasei {nume_clasa}: {e}")
        return None

def executa_metoda_pe_fire(nume_clasa, nume_metoda, nr_fire, argumente=None):
    cls = incarca_clasa_din_fisier(nume_clasa)
    if cls is None:
        return "CLASA_INDISPONIBILA"

    obiect = cls()
    metoda = getattr(obiect, nume_metoda, None)
    if metoda is None:
        return f"Eroare: metoda {nume_metoda} nu exista"

    rezultate = []

    def worker(arg):
        rezultat = metoda(arg)
        rezultate.append(rezultat)

    threaduri = []
    for i in range(nr_fire):
        if argumente and i < len(argumente):
            arg = argumente[i]
        else:
            print(f"[SERVER] Argument lipsa pentru firul {i}. Se omite executia.")
            continue
        t = threading.Thread(target=worker, args=(arg,))
        t.start()
        threaduri.append(t)

    for t in threaduri:
        t.join()

    return rezultate

def notifica_incarcare_actualizata(valoare, sursa=None):
    mesaj_id = str(uuid.uuid4())  
    for ip, port in clienti:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, port))
                s.sendall(pickle.dumps(("UPDATE_INCARCARE", valoare, sursa, mesaj_id)))
                print(f"[SERVER] Notificat clientul {ip}:{port} cu load: {valoare}")
        except Exception as e:
            print(f"[SERVER] Eroare notificare load catre {ip}:{port} - {e}")


def notifica_toti_clientii(nou_client_ip, nou_client_port):
    for ip, port in clienti:
        if (ip, port) == (nou_client_ip, nou_client_port):
            continue
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, port))
                s.sendall(pickle.dumps(("NOTIFICARE_CLIENT_NOU", (nou_client_ip, nou_client_port))))
                print(f"[SERVER] Notificat {ip}:{port} despre noul client {nou_client_ip}:{nou_client_port}")
        except Exception as e:
            print(f"[SERVER] Eroare notificare către {ip}:{port} - {e}")

def notifica_clienti_deconectare(ip_deconectat, port_deconectat):
    for ip, port in clienti:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((ip, port))
                s.sendall(pickle.dumps(("CLIENT_DECONECTAT", (ip_deconectat, port_deconectat), (MY_HOST, MY_PORT))))
                print(f"[SERVER] Notificat {ip}:{port} despre deconectarea {ip_deconectat}:{port_deconectat}")
        except Exception as e:
            print(f"[SERVER] Eroare notificare deconectare catre {ip}:{port} - {e}")

def gestioneaza_client(conn, addr):
    global incarcare_server
    try:
        data = pickle.loads(conn.recv(4096))

        if data[0] == "CONEXIUNE_CLIENT":
            ip_client, port_client = data[1]
            print(f"[SERVER] Client conectat: {ip_client}:{port_client}")
            clienti.append((ip_client, port_client))

            vecini_existenti = [c for c in clienti if c != (ip_client, port_client)]
            raspuns = {"status": "ok", "mesaj": "Conexiune reușită", "vecini": vecini_existenti}
            conn.sendall(pickle.dumps(raspuns))
            notifica_toti_clientii(ip_client, port_client)

        elif data[0] == "GET_INCARCARE":
            conn.sendall(pickle.dumps({"incarcare": incarcare_server}))

        elif data[0] == "EXECUTA_METODA":
            nume_clasa, nume_metoda, nr_fire, argumente = data[1]
            print(f"[SERVER] Execut metoda: {nume_clasa}.{nume_metoda} pe {nr_fire} fire")

            if not argumente or len(argumente) < nr_fire:
                print(f"[SERVER] Ai cerut {nr_fire} fire dar ai primit doar {len(argumente)} argumente.")

            incarcare_server += nr_fire
            notifica_incarcare_actualizata(incarcare_server, sursa=(MY_HOST, MY_PORT))

            rezultat = executa_metoda_pe_fire(nume_clasa, nume_metoda, nr_fire, argumente)

            incarcare_server -= nr_fire
            notifica_incarcare_actualizata(incarcare_server, sursa=(MY_HOST, MY_PORT))

            if rezultat == "CLASA_INDISPONIBILA":
                conn.sendall(pickle.dumps({"status": "clasa_lipsa"}))
                print(f"[SERVER] Clasa {nume_clasa} indisponibila pe server")
            else:
                conn.sendall(pickle.dumps({"status": "ok", "rezultate": rezultat}))
                print(f"[SERVER] Metoda executata. Rezultate trimise către client")

        elif data[0] == "TRIMITE_CLASA":
            nume_clasa, continut = data[1]
            try:
                with open(os.path.join(clase_path, f"{nume_clasa}.py"), "wb") as f:
                    f.write(continut)
                conn.sendall(pickle.dumps({"status": "clasa_primit"}))
                print(f"[SERVER] Clasa {nume_clasa} salvată cu succes")
            except Exception as e:
                conn.sendall(pickle.dumps({"status": "eroare", "mesaj": str(e)}))
                print(f"[SERVER] Eroare salvare clasa {nume_clasa} - {e}")

        elif data[0] == "CLIENT_DECONECTARE":
            ip_client, port_client = data[1]
            print(f"[SERVER] Clientul {ip_client}:{port_client} s-a deconectat manual")
            if (ip_client, port_client) in clienti:
                clienti.remove((ip_client, port_client))
                notifica_clienti_deconectare(ip_client, port_client)
            return

    except Exception as e:
        print(f"[SERVER] Eroare în gestionarea clientului: {e}")

    finally:
        try:
            if conn:
                ip, port = addr
                print(f"[SERVER] Inchidere conexiune cu {ip}:{port}")
                if (ip, port) in clienti:
                    clienti.remove((ip, port))
                    notifica_clienti_deconectare(ip, port)
        except:
            pass
        conn.close()


def porneste_server():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((MY_HOST, MY_PORT))
    s.listen()
    s.settimeout(1.0)  

    print(f"[SERVER] Server pornit. Asteapta conexiuni pe {MY_HOST}:{MY_PORT}")

    try:
        while True:
            try:
                conn, addr = s.accept()
                threading.Thread(target=gestioneaza_client, args=(conn, addr), daemon=True).start()
            except socket.timeout:
                continue 
    except KeyboardInterrupt:
        print("\n[SERVER] Inchidere manuala detectata. Serverul se oprește...")
        s.close()


if __name__ == "__main__":
    try:
        porneste_server()
    except KeyboardInterrupt:
        print("\n[SERVER] Serverul se opreste...")
