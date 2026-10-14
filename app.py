import re
from io import StringIO
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# =====================================================================
# ODKAZY NA OBĚ GOOGLE TABULKY:
# =====================================================================
URL_PRACE = "https://docs.google.com/spreadsheets/d/1r2IVopVO7eS5hBs96fGUKek8n5gKz4H21zplz8g9obk/edit?gid=0#gid=0"
URL_DOMOV = "https://docs.google.com/spreadsheets/d/1yJ8zTFR75XgCIWvaqhuH13XLEcsBhtVqQWSql5mbgw/edit?gid=0#gid=0"

st.set_page_config(
    page_title="Meteostanice Opava",
    page_icon="🌤️",
    layout="wide",
)

# 🔥 NEPRŮSTŘELNÝ GVIZ ENDPOINT (Google ho neblokuje přihlašovací stránkou) 🔥
def get_export_url(url: str) -> str:
    match_id = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    match_gid = re.search(r"[#&?]gid=([0-9]+)", url)

    if match_id:
        sheet_id = match_id.group(1)
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv"
        if match_gid:
            csv_url += f"&gid={match_gid.group(1)}"
        return csv_url
    return url


# =====================================================================
# NAČÍTÁNÍ DAT - PRÁCE
# =====================================================================
@st.cache_data(ttl=120)
def load_data_prace(url: str):
    csv_url = get_export_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(csv_url, headers=headers)
    
    if res.status_code != 200 or "<html" in res.text.lower():
        raise ValueError("Chyba při stahování tabulky z práce. Zkontroluj sdílení.")

    df = pd.read_csv(StringIO(res.text), header=None, sep=None, engine="python")
    df = df.dropna(how="all", axis=1)

    if df.shape[1] > 7:
        df = df.iloc[:, :7]
    elif df.shape[1] < 7:
        raise ValueError(f"Tabulka má jen {df.shape[1]} sloupců, očekává se 7.")

    df.columns = ["cas", "temp_in", "hum_in", "press_in", "temp_out", "hum_out", "press_out"]
    df["cas"] = pd.to_datetime(df["cas"], errors="coerce")
    df = df.dropna(subset=["cas"])

    numeric_cols = ["temp_in", "hum_in", "press_in", "temp_out", "hum_out", "press_out"]
    for col in numeric_cols:
        df[col] = df[col].astype(str).str.replace(",", ".").str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("cas").reset_index(drop=True)

    df["press_out"] = df["press_out"].replace(0, None).ffill()
    df["hum_out"] = df["hum_out"].replace(0, None).ffill()
    df["temp_out"] = df["temp_out"].replace(0, None).ffill()

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["mesic"] = df["cas"].dt.strftime("%Y-%m")
    df["den"] = df["cas"].dt.strftime("%Y-%m-%d")
    return df


# =====================================================================
# NAČÍTÁNÍ DAT - DOMOV
# =====================================================================
@st.cache_data(ttl=120)
def load_data_domov(url: str):
    csv_url = get_export_url(url)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(csv_url, headers=headers)
    
    if res.status_code != 200 or "<html" in res.text.lower():
        raise ValueError("Chyba při stahování tabulky domova.")

    df = pd.read_csv(StringIO(res.text), header=0, sep=None, engine="python")
    df = df.dropna(how="all", axis=1)

    df.columns = ["datum_raw", "cas_raw", "temp", "hum", "press", "pocasi"]

    df["datum_ciste"] = df["datum_raw"].astype(str).str.strip().apply(lambda x: x.split(" ")[-1] if " " in x else x)
    df["cas_cisty"] = df["cas_raw"].astype(str).str.strip()

    df["cas"] = pd.to_datetime(df["datum_ciste"] + " " + df["cas_cisty"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["cas"])

    numeric_cols = ["temp", "hum", "press"]
    for col in numeric_cols:
        df[col] = df[col].astype(str).str.replace(",", ".").str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("cas").reset_index(drop=True)
    df["mesic"] = df["cas"].dt.strftime("%Y-%m")
    df["den"] = df["cas"].dt.strftime("%Y-%m-%d")
    return df


# --- STAV NAVIGACE ---
if "level" not in st.session_state:
    st.session_state.level = "mesice"
    st.session_state.vybrany_mesic = None
    st.session_state.vybrany_den = None

# --- BOČNÍ PANEL S PŘEPÍNAČEM LOKALIT ---
st.sidebar.title("🌤️ Meteostanice")
lokalita = st.sidebar.radio("📍 Vyber lokalitu:", ["🏢 Práce (Jaktař)", "🏡 Domov (Holasická 6)"])

if st.sidebar.button("🔄 Zkontrolovat nová data"):
    st.cache_data.clear()
    st.rerun()

try:
    if "Práce" in lokalita:
        df = load_data_prace(URL_PRACE)
        posledni = df.iloc[-1]
        st.sidebar.success(f"Poslední měření:\n{posledni['cas'].strftime('%d.%m.%Y %H:%M')}")
        st.sidebar.metric("Teplota uvnitř", f"{posledni['temp_in']:.1f} °C")
        st.sidebar.metric("Teplota venku", f"{posledni['temp_out']:.1f} °C")
        st.sidebar.caption(f"Tlak: {posledni['press_in']:.1f} hPa | Vlhkost: {posledni['hum_in']:.0f}%")
    else:
        df = load_data_domov(URL_DOMOV)
        posledni = df.iloc[-1]
        st.sidebar.success(f"Poslední měření:\n{posledni['cas'].strftime('%d.%m.%Y %H:%M')}")
        st.sidebar.metric("Teplota venku", f"{posledni['temp']:.1f} °C")
        st.sidebar.metric("Stav počasí", f"{posledni['pocasi']}")
        st.sidebar.caption(f"Tlak: {posledni['press']:.1f} hPa | Vlhkost: {posledni['hum']:.0f}%")
except Exception as e:
    st.error(f"Chyba při načítání: {e}")
    st.stop()


# =====================================================================
# ZOBRAZENÍ: 🏢 PRÁCE (JAKTAŘ)
# =====================================================================
if "Práce" in lokalita:

    if st.session_state.level == "mesice":
        st.title("🏢 Práce (Jaktař) - Přehled měsíců")
        st.caption("Klikni na sloupec měsíce v grafu nebo ho vyber níže pro detail dnů:")

        mesicni = df.groupby("mesic").agg({
            "temp_in": "mean", "temp_out": "mean"
        }).reset_index().sort_values("mesic")

        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(
            x=mesicni["mesic"], y=mesicni["temp_in"], name="Uvnitř (°C)",
            text=[f"{float(x):.1f}°" for x in mesicni["temp_in"]], textposition="auto", marker_color="#E64A19"
        ))
        fig_m.add_trace(go.Bar(
            x=mesicni["mesic"], y=mesicni["temp_out"], name="Venku (°C)",
            text=[f"{float(x):.1f}°" for x in mesicni["temp_out"]], textposition="auto", marker_color="#1976D2"
        ))
        fig_m.update_layout(barmode="group", xaxis_title="Měsíc", yaxis_title="Průměrná teplota (°C)", clickmode="event+select")
        
        event_m = st.plotly_chart(fig_m, use_container_width=True, on_select="rerun", key="m_prace")
        if event_m and event_m.get("selection") and event_m["selection"].get("points"):
            kliknuty = event_m["selection"]["points"][0]["x"]
            if kliknuty in mesicni["mesic"].values:
                st.session_state.vybrany_mesic = kliknuty
                st.session_state.level = "dny"
                st.rerun()

        vybrany_m = st.selectbox("📅 Vyber měsíc ze seznamu:", ["-- Vyber měsíc --"] + mesicni["mesic"].tolist())
        if vybrany_m != "-- Vyber měsíc --":
            st.session_state.vybrany_mesic = vybrany_m
            st.session_state.level = "dny"
            st.rerun()

    elif st.session_state.level == "dny":
        mesic = st.session_state.vybrany_mesic
        if st.button("⬅️ Zpět na přehled měsíců"):
            st.session_state.level = "mesice"
            st.rerun()

        st.title(f"🏢 Práce - Denní průměry v měsíci {mesic}")
        df_mesic = df[df["mesic"] == mesic]
        denni = df_mesic.groupby("den").agg({"temp_in": "mean", "temp_out": "mean"}).reset_index().sort_values("den")

        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(
            x=denni["den"], y=denni["temp_in"], name="Uvnitř (°C)",
            text=[f"{float(x):.1f}°" for x in denni["temp_in"]], textposition="auto", marker_color="#E64A19"
        ))
        fig_d.add_trace(go.Bar(
            x=denni["den"], y=denni["temp_out"], name="Venku (°C)",
            text=[f"{float(x):.1f}°" for x in denni["temp_out"]], textposition="auto", marker_color="#1976D2"
        ))
        fig_d.update_layout(barmode="group", xaxis_title="Den", yaxis_title="Průměrná teplota (°C)", clickmode="event+select")
        
        event_d = st.plotly_chart(fig_d, use_container_width=True, on_select="rerun", key="d_prace")
        if event_d and event_d.get("selection") and event_d["selection"].get("points"):
            kliknuty = event_d["selection"]["points"][0]["x"]
            if kliknuty in denni["den"].values:
                st.session_state.vybrany_den = kliknuty
                st.session_state.level = "detail"
                st.rerun()

        vybrany_d = st.selectbox("📆 Vyber konkrétní den pro detailní průběh:", ["-- Vyber den --"] + denni["den"].tolist())
        if vybrany_d != "-- Vyber den --":
            st.session_state.vybrany_den = vybrany_d
            st.session_state.level = "detail"
            st.rerun()

    elif st.session_state.level == "detail":
        den = st.session_state.vybrany_den
        if st.button("⬅️ Zpět na dny"):
            st.session_state.level = "dny"
            st.rerun()

        st.title(f"📈 Práce - Detailní průběh: {den}")
        den_data = df[df["den"] == den].sort_values("cas")

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Teplota Uvnitř", f"{den_data['temp_in'].mean():.1f} °C", f"max {den_data['temp_in'].max():.1f} °C")
        kpi2.metric("Teplota Venku", f"{den_data['temp_out'].mean():.1f} °C", f"max {den_data['temp_out'].max():.1f} °C")
        kpi3.metric("Vlhkost (Uvnitř / Venku)", f"{den_data['hum_in'].mean():.0f}% / {den_data['hum_out'].mean():.0f}%")
        kpi4.metric("Tlak (Uvnitř / Venku)", f"{den_data['press_in'].mean():.1f} / {den_data['press_out'].mean():.1f} hPa")

        st.divider()

        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(x=den_data["cas"], y=den_data["temp_in"], mode="lines+markers", name="Uvnitř (°C)", line=dict(color="#E64A19", width=2)))
        fig_temp.add_trace(go.Scatter(x=den_data["cas"], y=den_data["temp_out"], mode="lines+markers", name="Venku (°C)", line=dict(color="#1976D2", width=2)))
        fig_temp.update_layout(title="Průběh teploty v čase", xaxis_title="Čas", yaxis_title="Teplota (°C)", hovermode="x unified")
        st.plotly_chart(fig_temp, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            fig_hum = go.Figure()
            fig_hum.add_trace(go.Scatter(x=den_data["cas"], y=den_data["hum"], name="Uvnitř (%)", line=dict(color="#00ACC1")))
            fig_hum.add_trace(go.Scatter(x=den_data["cas"], y=den_data["hum_out"], name="Venku (%)", line=dict(color="#43A047")))
            fig_hum.update_layout(title="Průběh vlhkosti (%)", xaxis_title="Čas", yaxis_title="Vlhkost (%)", hovermode="x unified")
            st.plotly_chart(fig_hum, use_container_width=True)
        with c2:
            fig_press = go.Figure()
            fig_press.add_trace(go.Scatter(x=den_data["cas"], y=den_data["press_in"], name="Uvnitř (hPa)", line=dict(color="#FB8C00")))
            fig_press.add_trace(go.Scatter(x=den_data["cas"], y=den_data["press_out"], name="Venku (hPa)", line=dict(color="#8E24AA")))
            fig_press.update_layout(title="Průběh tlaku (hPa)", xaxis_title="Čas", yaxis_title="Tlak (hPa)", hovermode="x unified")
            st.plotly_chart(fig_press, use_container_width=True)


# =====================================================================
# ZOBRAZENÍ: 🏡 DOMOV (HOLASICKÁ 6)
# =====================================================================
else:
    if st.session_state.level == "mesice":
        st.title("🏡 Domov (Holasická 6) - Přehled měsíců")
        st.caption("Klikni na sloupec měsíce v grafu nebo ho vyber níže pro detail dnů:")

        mesicni = df.groupby("mesic").agg({"temp": "mean"}).reset_index().sort_values("mesic")

        fig_m = go.Figure()
        fig_m.add_trace(go.Bar(
            x=mesicni["mesic"], y=mesicni["temp"], name="Teplota (°C)",
            text=[f"{float(x):.1f}°" for x in mesicni["temp"]], textposition="auto", marker_color="#2E7D32"
        ))
        fig_m.update_layout(xaxis_title="Měsíc", yaxis_title="Průměrná teplota (°C)", clickmode="event+select")
        
        event_m = st.plotly_chart(fig_m, use_container_width=True, on_select="rerun", key="m_doma")
        if event_m and event_m.get("selection") and event_m["selection"].get("points"):
            kliknuty = event_m["selection"]["points"][0]["x"]
            if kliknuty in mesicni["mesic"].values:
                st.session_state.vybrany_mesic = kliknuty
                st.session_state.level = "dny"
                st.rerun()

        vybrany_m = st.selectbox("📅 Vyber měsíc ze seznamu:", ["-- Vyber měsíc --"] + mesicni["mesic"].tolist())
        if vybrany_m != "-- Vyber měsíc --":
            st.session_state.vybrany_mesic = vybrany_m
            st.session_state.level = "dny"
            st.rerun()

    elif st.session_state.level == "dny":
        mesic = st.session_state.vybrany_mesic
        if st.button("⬅️ Zpět na přehled měsíců"):
            st.session_state.level = "mesice"
            st.rerun()

        st.title(f"🏡 Domov - Denní průměry v měsíci {mesic}")
        df_mesic = df[df["mesic"] == mesic]
        denni = df_mesic.groupby("den").agg({"temp": "mean"}).reset_index().sort_values("den")

        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(
            x=denni["den"], y=denni["temp"], name="Teplota (°C)",
            text=[f"{float(x):.1f}°" for x in denni["temp"]], textposition="auto", marker_color="#2E7D32"
        ))
        fig_d.update_layout(xaxis_title="Den", yaxis_title="Průměrná teplota (°C)", clickmode="event+select")
        
        event_d = st.plotly_chart(fig_d, use_container_width=True, on_select="rerun", key="d_doma")
        if event_d and event_d.get("selection") and event_d["selection"].get("points"):
            kliknuty = event_d["selection"]["points"][0]["x"]
            if kliknuty in denni["den"].values:
                st.session_state.vybrany_den = kliknuty
                st.session_state.level = "detail"
                st.rerun()

        vybrany_d = st.selectbox("📆 Vyber konkrétní den pro detailní průběh:", ["-- Vyber den --"] + denni["den"].tolist())
        if vybrany_d != "-- Vyber den --":
            st.session_state.vybrany_den = vybrany_d
            st.session_state.level = "detail"
            st.rerun()

    elif st.session_state.level == "detail":
        den = st.session_state.vybrany_den
        if st.button("⬅️ Zpět na dny"):
            st.session_state.level = "dny"
            st.rerun()

        st.title(f"📈 Domov - Detailní průběh: {den}")
        den_data = df[df["den"] == den].sort_values("cas")

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Průměrná teplota", f"{den_data['temp'].mean():.1f} °C", f"max {den_data['temp'].max():.1f} °C")
        kpi2.metric("Průměrná vlhkost", f"{den_data['hum'].mean():.0f}%")
        kpi3.metric("Průměrný tlak", f"{den_data['press'].mean():.1f} hPa")

        st.divider()

        fig_temp = go.Figure()
        fig_temp.add_trace(go.Scatter(
            x=den_data["cas"], y=den_data["temp"],
            mode="lines+markers", name="Teplota (°C)",
            line=dict(color="#2E7D32", width=2),
            text=den_data["pocasi"],
            hovertemplate="%{x|%H:%M}<br>Teplota: <b>%{y:.1f} °C</b><br>Stav: %{text}<extra></extra>"
        ))
        fig_temp.update_layout(title="Průběh teploty na Holasické", xaxis_title="Čas", yaxis_title="Teplota (°C)", hovermode="x unified")
        st.plotly_chart(fig_temp, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            fig_hum = go.Figure()
            fig_hum.add_trace(go.Scatter(x=den_data["cas"], y=den_data["hum"], name="Vlhkost (%)", line=dict(color="#0288D1")))
            fig_hum.update_layout(title="Průběh vlhkosti (%)", xaxis_title="Čas", yaxis_title="Vlhkost (%)", hovermode="x unified")
            st.plotly_chart(fig_hum, use_container_width=True)
        with c2:
            fig_press = go.Figure()
            fig_press.add_trace(go.Scatter(x=den_data["cas"], y=den_data["press"], name="Tlak (hPa)", line=dict(color="#7B1FA2")))
            fig_press.update_layout(title="Průběh tlaku (hPa)", xaxis_title="Čas", yaxis_title="Tlak (hPa)", hovermode="x unified")
            st.plotly_chart(fig_press, use_container_width=True)
