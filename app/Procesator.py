class Procesator:
    def proceseaza(self, valoare): 
        rezultat = 0
        for i in range(10**7):
            rezultat += (i % 5 + valoare) 
        return rezultat
