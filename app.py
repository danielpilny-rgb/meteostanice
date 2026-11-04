import re
from io import StringIO
import math
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# =================================================================
# 1. ODKAZY NA TVÉ GOOGLE TABULKY
# =================================================================
URL_PRACE   = "https://docs.google.com/spreadsheets/d/1r2IVopVO7eS5hBs96fGUKek8n5gKz4H21zplz8g9obk/edit?gid=0#gid=0"
URL_DOMOV   = "https://docs.google.com/spreadsheets/d/1yJ8zTFR75XgCIWvaqhuH13XLEcsBhtVqQWsSql5mbgw/edit?gid=0#gid=0"
# 👇 SEM VLOŽ ODKAZ NA SVOU TABULKU S LETADLY (mezi uvozovky):
URL_LETADLA = "https://docs.google.com/spreadsheets/d/14ZaRb5FNlVZkkkV0TYVH0tJpFO9GjvJLeSm5kSN43Gk/edit?gid=0#gid=0" 

st.set_page_config(page_title="Meteo & Radar Opava", page_icon="🌤️", layout="wide")

def get_export_url(url: str) -> str:
    match_id = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    match_gid = re.search(r"[#&?]gid=([0-9]+)", url)
    if match_id:
        csv_url = f"https://docs.google.com/spreadsheets/d/{match_id.group(1)}/export?format=csv"
        if match_gid:
            csv_url += f"&gid={match_gid.group(1)}"
        return csv_url
    return url

# =================================================================
# 2. NAČÍTÁNÍ METEO DAT (PRÁCE A DOMOV)
# =================================================================
@st.cache_data(ttl=120)
def load_data_prace(url: str):
    res = requests.get(get_export_url(url), headers={"User-Agent": "Mozilla/5.0"})
    df = pd.read_csv(StringIO(res.text), header=None, sep=None, engine="python").dropna(how="all", axis=1).iloc[:, :7]
    df.columns = ["cas", "temp_in", "hum_in", "press_in", "temp_out", "hum_out", "press_out"]
    df["cas"] = pd.to_datetime(df["cas"], errors="coerce")
    df = df.dropna(subset=["cas"])
    for col in ["temp_in", "hum_in", "press_in", "temp_out", "hum_out", "press_out"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ".").str.strip(), errors="coerce")
    df = df.sort_values("cas").reset_index(drop=True)
    df["press_out"] = df["press_out"].replace(0, None).ffill()
    df["hum_out"]   = df["hum_out"].replace(0, None).ffill()
    df["temp_out"]  = df["temp_out"].replace(0, None).ffill()
    df["mesic"] = df["cas"].dt.strftime("%Y-%m")
    df["den"]   = df["cas"].dt.strftime("%Y-%m-%d")
    return df

@st.cache_data(ttl=120)
def load_data_domov(url: str):
    res = requests.get(get_export_url(url), headers={"User-Agent": "Mozilla/5.0"})
    df = pd.read_csv(StringIO(res.text), header=0, sep=None, engine="python").dropna(how="all", axis=1)
    df.columns = ["datum_raw", "cas_raw", "temp", "hum", "press", "pocasi"]
    df["datum_ciste"] = df["datum_raw"].astype(str).str.strip().apply(lambda x: x.split(" ")[-1] if " " in x else x)
    df["cas"] = pd.to_datetime(df["datum_ciste"] + " " + df["cas_raw"].astype(str).str.strip(), dayfirst=True, errors="coerce")
    df = df.dropna(subset=["cas"])
    for col in ["temp", "hum", "press"]:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ".").str.strip(), errors="coerce")
    df = df.sort_values("cas").reset_index(drop=True)
    df["mesic"] = df["cas"].dt.strftime("%Y-%m")
    df["den"]   = df["cas"].dt.strftime("%Y-%m-%d")
    return df

# =================================================================
# 3. DATABÁZE AEROLINEK A ANALÝZA LETADEL
# =================================================================
AIRLINES = {
    "RYR": "Ryanair 🟡", "RYS": "Buzz (Ryanair) 🟡",
    "WZZ": "Wizz Air 🟣", "WMT": "Wizz Air Malta 🟣", "WUK": "Wizz Air UK 🟣",
    "DLH": "Lufthansa 🇩🇪", "LOT": "LOT Polish Airlines 🇵🇱",
    "ENT": "Enter Air 🇵🇱", "THY": "Turkish Airlines 🇹🇷",
    "ASL": "Air Serbia 🇷🇸", "VKG": "Sunclass Airlines ☀️",
    "BTI": "airBaltic 🇱🇻", "SCT": "Smartwings / Charter 🇨🇿",
    "BLX": "TUIfly Nordic ✈️", "EWG": "Eurowings 🇩🇪",
    "EJU": "easyJet Europe 🟠", "EZY": "easyJet 🟠",
    "FIN": "Finnair 🇫🇮", "AEE": "Aegean Airlines 🇬🇷",
    "PGT": "Pegasus Airlines 🇹🇷", "SDR": "Sundair 🇩🇪",
    "SAS": "Scandinavian Airlines (SAS) 🇸🇪", "QTR": "Qatar Airways 🇶🇦",
    "NOZ": "Norwegian 🇳🇴", "NAX": "Norwegian 🇳🇴",
    "MFX": "Air Pink (VIP Jet) 🛩️", "AUA": "Austrian Airlines 🇦🇹",
    "BAW": "British Airways 🇬🇧", "KLM": "KLM Royal Dutch 🇳🇱",
    "AFR": "Air France 🇫🇷", "UAE": "Emirates 🇦🇪",
    "TVS": "Smartwings 🇨🇿", "CSA": "ČSA 🇨🇿"
}

def urci_aerolinku(callsign):
    callsign = str(callsign).strip().upper()
    if callsign.startswith("ID:"):
        return "Neznámý / Armáda 🪖"
    if callsign.startswith("OK"):
        return "Soukromý let (ČR) 🇨🇿"
    if callsign.startswith("SP"):
        return "Soukromý let (Polsko) 🇵🇱"
    if callsign.startswith("OE"):
        return "Soukromý let (Rakousko) 🇦🇹"
    if callsign.startswith("D-"):
        return "Soukromý let (Německo) 🇩🇪"
    
    prefix = callsign[:3]
    return AIRLINES.get(prefix, "Ostatní / Charter ✈️")

AIRPORTS = {
    "verona": (45.39, 10.88), "palermo": (38.17, 13.09), "rome": (41.80, 12.23), "milan": (45.63, 8.72),
    "warsaw": (52.16, 20.96), "krakow": (50.07, 19.78), "gdańsk": (54.37, 18.46), "gdansk": (54.37, 18.46),
    "berlin": (52.36, 13.50), "frankfurt am main": (50.03, 8.57), "frankfurt": (50.03, 8.57), "stuttgart": (48.68, 9.22), "hamburg": (53.63, 9.99),
    "istanbul": (41.27, 28.72), "arnavutkoy, istanbul": (41.27, 28.72), "antalya": (36.89, 30.80), "bodrum": (37.25, 27.66), "gaziantep": (36.94, 37.47),
    "copenhagen": (55.61, 12.65), "stockholm": (59.65, 17.91), "gothenburg": (57.66, 12.27), "helsinki": (60.31, 24.96), "riga": (56.92, 23.97),
    "barcelona": (41.29, 2.08), "nice": (43.65, 7.21), "lyon": (45.72, 5.08), "birmingham": (52.45, -1.74), "brussels": (50.90, 4.48),
    "larnaca": (34.87, 33.62), "beirut": (33.82, 35.48), "valletta": (35.85, 14.47), "budapest": (47.43, 19.25), "vienna": (48.11, 16.56)
}

def geo_dist(lat1, lon1, lat2, lon2):
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return 6371.0 * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def analyzuj_let(row):
    callsign = str(row["linka"]).strip()
    trasa = str(row["trasa"]).strip()
    model = str(row["model"]).strip()
    vyska = row["vyska"]
    
    if callsign.startswith("ID:") or trasa == "---" or trasa == "":
        return "🟡 INFO: Bez letového plánu (Vojenský / Vládní)"
    if model.lower() == "neznamy" or model == "":
        return "🟡 INFO: Neznámý typ letounu"

    if "->" in trasa:
        parts = trasa.split("->")
        orig = parts[0].strip().lower()
        dest = parts[1].strip().lower()
        if orig in AIRPORTS and dest in AIRPORTS:
            o_lat, o_lon = AIRPORTS[orig]
            d_lat, d_lon = AIRPORTS[dest]
            d_direct = geo_dist(o_lat, o_lon, d_lat, d_lon)
            d_via_opava = geo_dist(o_lat, o_lon, 49.94, 17.91) + geo_dist(49.94, 17.91, d_lat, d_lon)
            if d_via_opava > (d_direct * 1.40) and (d_via_opava - d_direct > 300):
                return "🔴 POZOR: Poloha letadla neodpovídá trase!"

    if vyska < 3500 and vyska > 0:
        return "🔵 INFO: Nízký průlet / Přiblížení"

    return "🟢 OK"

@st.cache_data(ttl=120)
def load_data_letadla(url: str):
    res = requests.get(get_export_url(url), headers={"User-Agent": "Mozilla/5.0"})
    df = pd.read_csv(StringIO(res.text), header=0, sep=None, engine="python").dropna(how="all", axis=1)
    df.columns = ["datum", "cas", "linka", "trasa", "model", "vzdalenost", "vyska", "rychlost"]
    
    df["vzdalenost"] = pd.to_numeric(df["vzdalenost"].astype(str).str.replace(",", ".").str.strip(), errors="coerce")
    df["vyska"]       = pd.to_numeric(df["vyska"].astype(str).str.replace(",", ".").str.strip(), errors="coerce").fillna(0)
    df["rychlost"]    = pd.to_numeric(df["rychlost"].astype(str).str.replace(",", ".").str.strip(), errors="coerce").fillna(0)
    
# Převod na skutečný čas, aby 5:52 bylo před 10:00
    df["cas_dt"] = pd.to_datetime(df["datum"] + " " + df["cas"], dayfirst=True, errors="coerce")
    df = df.sort_values("vzdalenost").drop_duplicates(subset=["datum", "linka"], keep="first")
    df = df.sort_values("cas_dt").reset_index(drop=True)
    df["aerolinka"] = df["linka"].apply(urci_aerolinku)
    df["status"] = df.apply(analyzuj_let, axis=1)
    return df

# =================================================================
# 4. SIDEBAR - PŘEPÍNÁNÍ MODULŮ
# =================================================================
st.sidebar.title("🧭 Ovládací panel")
modul = st.sidebar.radio("📍 Vyber zobrazení:", [
    "🏢 Práce (Jaktař) - Počasí", 
    "🏡 Domov (Holasická 6) - Počasí",
    "✈️ Letecký radar (Opava)"
])

if st.sidebar.button("🔄 Zkontrolovat nová data"):
    st.cache_data.clear()
    st.rerun()

# =================================================================
# MODUL 1 & 2: METEOSTANICE (PRÁCE / DOMOV)
# =================================================================
if "Počasí" in modul:
    if "level" not in st.session_state:
        st.session_state.level = "mesice"
        st.session_state.vybrany_mesic = None
        st.session_state.vybrany_den = None

    if "Práce" in modul:
        df = load_data_prace(URL_PRACE)
        posledni = df.iloc[-1]
        st.sidebar.success(f"Poslední měření:\n{posledni['cas'].strftime('%d.%m.%Y %H:%M')}")
        st.sidebar.metric("Teplota uvnitř", f"{posledni['temp_in']:.1f} °C")
        st.sidebar.metric("Teplota venku", f"{posledni['temp_out']:.1f} °C")
        st.sidebar.caption(f"Tlak: {posledni['press_in']:.1f} hPa | Vlhkost: {posledni['hum_in']:.0f}%")

        if st.session_state.level == "mesice":
            st.title("🏢 Práce (Jaktař) - Přehled měsíců")
            mesicni = df.groupby("mesic").agg({"temp_in": "mean", "temp_out": "mean"}).reset_index().sort_values("mesic")
            fig_m = go.Figure([
                go.Bar(x=mesicni["mesic"], y=mesicni["temp_in"], name="Uvnitř (°C)", text=[f"{x:.1f}°" for x in mesicni["temp_in"]], textposition="auto", marker_color="#E64A19"),
                go.Bar(x=mesicni["mesic"], y=mesicni["temp_out"], name="Venku (°C)", text=[f"{x:.1f}°" for x in mesicni["temp_out"]], textposition="auto", marker_color="#1976D2")
            ])
            fig_m.update_layout(barmode="group", xaxis_title="Měsíc", yaxis_title="Průměrná teplota (°C)")
            st.plotly_chart(fig_m, use_container_width=True)
            vybrany_m = st.selectbox("📅 Vyber měsíc:", ["-- Vyber měsíc --"] + mesicni["mesic"].tolist())
            if vybrany_m != "-- Vyber měsíc --":
                st.session_state.vybrany_mesic = vybrany_m
                st.session_state.level = "dny"
                st.rerun()

        elif st.session_state.level == "dny":
            mesic = st.session_state.vybrany_mesic
            if st.button("⬅️ Zpět na přehled měsíců"): st.session_state.level = "mesice"; st.rerun()
            st.title(f"🏢 Práce - Denní průměry v měsíci {mesic}")
            denni = df[df["mesic"] == mesic].groupby("den").agg({"temp_in": "mean", "temp_out": "mean"}).reset_index().sort_values("den")
            fig_d = go.Figure([
                go.Bar(x=denni["den"], y=denni["temp_in"], name="Uvnitř (°C)", text=[f"{x:.1f}°" for x in denni["temp_in"]], textposition="auto", marker_color="#E64A19"),
                go.Bar(x=denni["den"], y=denni["temp_out"], name="Venku (°C)", text=[f"{x:.1f}°" for x in denni["temp_out"]], textposition="auto", marker_color="#1976D2")
            ])
            fig_d.update_layout(barmode="group", xaxis_title="Den", yaxis_title="Průměrná teplota (°C)")
            st.plotly_chart(fig_d, use_container_width=True)
            vybrany_d = st.selectbox("📆 Vyber konkrétní den:", ["-- Vyber den --"] + denni["den"].tolist())
            if vybrany_d != "-- Vyber den --":
                st.session_state.vybrany_den = vybrany_d
                st.session_state.level = "detail"
                st.rerun()

        elif st.session_state.level == "detail":
            den = st.session_state.vybrany_den
            if st.button("⬅️ Zpět na dny"): st.session_state.level = "dny"; st.rerun()
            st.title(f"📈 Práce - Detailní průběh: {den}")
            den_data = df[df["den"] == den].sort_values("cas")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Teplota Uvnitř", f"{den_data['temp_in'].mean():.1f} °C", f"max {den_data['temp_in'].max():.1f} °C")
            k2.metric("Teplota Venku", f"{den_data['temp_out'].mean():.1f} °C", f"max {den_data['temp_out'].max():.1f} °C")
            k3.metric("Vlhkost", f"{den_data['hum_in'].mean():.0f}% / {den_data['hum_out'].mean():.0f}%")
            k4.metric("Tlak", f"{den_data['press_in'].mean():.1f} / {den_data['press_out'].mean():.1f} hPa")
            st.divider()
            fig_temp = go.Figure([
                go.Scatter(x=den_data["cas"], y=den_data["temp_in"], mode="lines+markers", name="Uvnitř (°C)", line=dict(color="#E64A19", width=2)),
                go.Scatter(x=den_data["cas"], y=den_data["temp_out"], mode="lines+markers", name="Venku (°C)", line=dict(color="#1976D2", width=2))
            ])
            st.plotly_chart(fig_temp, use_container_width=True)

    else:
        df = load_data_domov(URL_DOMOV)
        posledni = df.iloc[-1]
        st.sidebar.success(f"Poslední měření:\n{posledni['cas'].strftime('%d.%m.%Y %H:%M')}")
        st.sidebar.metric("Teplota venku", f"{posledni['temp']:.1f} °C")
        st.sidebar.metric("Stav počasí", f"{posledni['pocasi']}")
        st.sidebar.caption(f"Tlak: {posledni['press']:.1f} hPa | Vlhkost: {posledni['hum']:.0f}%")

        if st.session_state.level == "mesice":
            st.title("🏡 Domov (Holasická 6) - Přehled měsíců")
            mesicni = df.groupby("mesic").agg({"temp": "mean"}).reset_index().sort_values("mesic")
            fig_m = go.Figure([go.Bar(x=mesicni["mesic"], y=mesicni["temp"], name="Teplota (°C)", text=[f"{x:.1f}°" for x in mesicni["temp"]], textposition="auto", marker_color="#2E7D32")])
            st.plotly_chart(fig_m, use_container_width=True)
            vybrany_m = st.selectbox("📅 Vyber měsíc:", ["-- Vyber měsíc --"] + mesicni["mesic"].tolist())
            if vybrany_m != "-- Vyber měsíc --": st.session_state.vybrany_mesic = vybrany_m; st.session_state.level = "dny"; st.rerun()

        elif st.session_state.level == "dny":
            mesic = st.session_state.vybrany_mesic
            if st.button("⬅️ Zpět na přehled měsíců"): st.session_state.level = "mesice"; st.rerun()
            st.title(f"🏡 Domov - Denní průměry v měsíci {mesic}")
            denni = df[df["mesic"] == mesic].groupby("den").agg({"temp": "mean"}).reset_index().sort_values("den")
            fig_d = go.Figure([go.Bar(x=denni["den"], y=denni["temp"], name="Teplota (°C)", text=[f"{x:.1f}°" for x in denni["temp"]], textposition="auto", marker_color="#2E7D32")])
            st.plotly_chart(fig_d, use_container_width=True)
            vybrany_d = st.selectbox("📆 Vyber konkrétní den:", ["-- Vyber den --"] + denni["den"].tolist())
            if vybrany_d != "-- Vyber den --": st.session_state.vybrany_den = vybrany_d; st.session_state.level = "detail"; st.rerun()

        elif st.session_state.level == "detail":
            den = st.session_state.vybrany_den
            if st.button("⬅️ Zpět na dny"): st.session_state.level = "dny"; st.rerun()
            st.title(f"📈 Domov - Detailní průběh: {den}")
            den_data = df[df["den"] == den].sort_values("cas")
            k1, k2, k3 = st.columns(3)
            k1.metric("Průměrná teplota", f"{den_data['temp'].mean():.1f} °C", f"max {den_data['temp'].max():.1f} °C")
            k2.metric("Průměrná vlhkost", f"{den_data['hum'].mean():.0f}%")
            k3.metric("Průměrný tlak", f"{den_data['press'].mean():.1f} hPa")
            st.divider()
            fig_temp = go.Figure([go.Scatter(x=den_data["cas"], y=den_data["temp"], mode="lines+markers", name="Teplota (°C)", line=dict(color="#2E7D32", width=2), text=den_data["pocasi"], hovertemplate="%{x|%H:%M}<br>Teplota: <b>%{y:.1f} °C</b><br>Stav: %{text}<extra></extra>")])
            st.plotly_chart(fig_temp, use_container_width=True)

# =================================================================
# MODUL 3: LETECKÝ RADAR (S PROVOZOVATELI)
# =================================================================
else:
    st.title("✈️ Letecký radar (Vzdušný prostor Opava)")
    try:
        df_air = load_data_letadla(URL_LETADLA)
    except Exception as e:
        st.error(f"Nepodařilo se načíst data letadel. Zkontroluj odkaz na tabulku v kódu. Chyba: {e}")
        st.stop()

    dny_v_tabulce = df_air["datum"].unique().tolist()
    vybrany_den = st.sidebar.selectbox("📅 Vyber den sledování:", dny_v_tabulce, index=len(dny_v_tabulce)-1)

    df_den = df_air[df_air["datum"] == vybrany_den].copy()

    # 1. Metriky v horním panelu
    c1, c2, c3, c4 = st.columns(4)
    celkem = len(df_den)
    pocet_pozor = len(df_den[df_den["status"].str.contains("POZOR")])
    pocet_info  = len(df_den[df_den["status"].str.contains("INFO")])
    pocet_ok    = len(df_den[df_den["status"].str.contains("OK")])

    c1.metric("Celkem přeletů", celkem)
    c2.metric("🟢 Běžné tranzity", pocet_ok)
    c3.metric("🟡 Zvláštní lety (INFO)", pocet_info)
    c4.metric("🔴 Podezřelé lety (POZOR)", pocet_pozor)

    st.divider()

    # 2. Vytahovák na anomálie
    anomalie = df_den[df_den["status"].str.contains("POZOR")]
    if len(anomalie) > 0:
        st.subheader("⚠️ Dnešní detekované anomálie")
        for _, let in anomalie.iterrows():
            st.error(f"""
            **🔴 {let['status']}**  
            * **Let:** `{let['linka']}` ({let['aerolinka']}) | **Čas:** `{let['cas']}`  
            * **Trasa v plánu:** `{let['trasa']}`  
            * **Model:** `{let['model']}`  
            * **Min. vzdálenost od Opavy:** `{let['vzdalenost']:.1f} km` | **Výška:** `{int(let['vyska'])} m` | **Rychlost:** `{int(let['rychlost'])} km/h`  
            """)

    zvlastni = df_den[df_den["status"].str.contains("INFO")]
    if len(zvlastni) > 0:
        with st.expander(f"🟡 Zobrazit zajímavé / vojenské lety ({len(zvlastni)})"):
            for _, let in zvlastni.iterrows():
                st.warning(f"**{let['status']}** — `{let['linka']}` ({let['aerolinka']}) v {let['cas']} ({let['model']}, trasa: {let['trasa']})")

    st.divider()

    # 3. Filtry a tabulka s novým sloupcem "Společnost"
    st.subheader(f"📋 Seznam všech přeletů dne ({vybrany_den})")
    filtr_stav = st.radio("Filtrovat podle stavu:", ["Vše", "Pouze 🔴 POZOR", "Pouze 🟡 INFO", "Pouze 🟢 OK"], horizontal=True)

    if filtr_stav == "Pouze 🔴 POZOR":
        df_zobrazit = df_den[df_den["status"].str.contains("POZOR")]
    elif filtr_stav == "Pouze 🟡 INFO":
        df_zobrazit = df_den[df_den["status"].str.contains("INFO")]
    elif filtr_stav == "Pouze 🟢 OK":
        df_zobrazit = df_den[df_den["status"].str.contains("OK")]
    else:
        df_zobrazit = df_den

    st.dataframe(
        df_zobrazit[["cas", "linka", "aerolinka", "trasa", "model", "vzdalenost", "vyska", "rychlost", "status"]],
        column_config={
            "cas": "Čas",
            "linka": "Linka",
            "aerolinka": "Společnost / Provozovatel",
            "trasa": "Trasa (Odkud -> Kam)",
            "model": "Typ letadla",
            "vzdalenost": st.column_config.NumberColumn("Vzdálenost (km)", format="%.1f km"),
            "vyska": st.column_config.NumberColumn("Výška (m)", format="%d m"),
            "rychlost": st.column_config.NumberColumn("Rychlost (km/h)", format="%d km/h"),
            "status": "Vyhodnocení"
        },
        use_container_width=True,
        hide_index=True
    )
