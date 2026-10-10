# Keihäänheitto

Peli + pieni Python-palvelin (ei riippuvuuksia). Omat ennätykset tallentuvat puhelimen localStorageen,
yhteiset ennätykset GitHubiin (`scores.json`, haara `scores`).

## Käyttöönotto
1. Luo **yksityinen** GitHub-repo ja lataa kaikki nämä tiedostot `main`-haaraan.
2. GitHub → Settings → Developer settings → Fine-grained token: vain tämä repo, oikeus *Contents: Read and write*.
3. Render → New → Blueprint (tai Web Service) → valitse repo. Aseta ympäristömuuttujat:
   - `GITHUB_TOKEN` = token
   - `GITHUB_REPO` = `kayttaja/repon-nimi`
   - (`GITHUB_BRANCH` = `scores`, palvelin luo haaran itse)
4. Avaa Renderin osoite Chromessa puhelimella → ⋮ → *Asenna sovellus*.

Tulokset commitataan haaraan `scores`, joten ne eivät käynnistä Renderiä uudelleen.
Siirrä vanhat ennätykset: vanhassa versiossa avaa `http://localhost:8765/data`, kopioi teksti,
uudessa pelissä valikko → *Tuo tiedot*.
