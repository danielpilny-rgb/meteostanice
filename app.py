import re
from io import StringIO
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# =====================================================================
# TVŮJ ODKAZ NA GOOGLE TABULKU:
# =====================================================================
URL_TVOJE_TABULKY = "https://docs.google.com/spreadsheets/d/1r2IVopVO7eS5hBs96fGUKek8n5gKz4H21zplz8g9obk/edit?gid=0#gid=0"  # tvůj odkaz

st.set_page_config(
    page_title="DIY Meteostanice",
    page_icon="🌡️",
    layout="wide",
)


def get_export_url(url: str) -> str:
    match_id = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
    match_gid = re.search(r"[#&?]gid=([0-9]+)", url)

    if match_id:
        sheet_id = match_id.group(1)
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
        if match_gid:
            csv_url += f"&gid={match_gid.group(1)}"
        return csv_url
    return url


@st.cache_data(ttl=120)
def load_data(url: str):
    csv_url = get_export_url(url)
    res = requests.get(csv_url)

    if res.status_code != 200:
        raise ValueError(f"Chyba stahování {res.status_code}. Zkontroluj sdílení.")
    if "<html" in res.text.lower():
        raise ValueError("Google poslal přihlašovací stránku. Zkontroluj sdílení.")

    df = pd.read_csv(StringIO(res.text), header=None, sep=None, engine="python")
    df = df.dropna(how="all", axis=1)

    if df.shape[1] > 7:
        df = df.iloc[:, :7]
    elif df.shape[1] < 7:
        raise ValueError(f"Tabulka má jen {df.shape[1]} sloupců, očekává se 7.")

    df.columns = ["cas", "temp_in", "hum_in", "press_in", "temp_out", "hum_out", "press_out"]
    df["cas"] = pd.to_datetime(df["cas"], errors="coerce")
    df = df.dropna(subset=["cas"])

    if df.empty:
        raise ValueError("Nenalezena žádná platná data s časem.")

    numeric_cols = ["temp_in", "hum_in", "press_in", "temp_out", "hum_out", "press_out"]
    for col in numeric_cols:
        df[col] = df[col].astype(str).str.replace(",", ".").str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values("cas").reset_index(drop=True)

    # Ošetření výpadků venkovních senzorů (nuly nahradíme předchozí hodnotou)
    df["press_out"] = df["press_out"].replace(0, None).ffill()
    df["hum_out"] = df["hum_out"].replace(0, None).ffill()
    df["temp_out"] = df["temp_out"].replace(0, None).ffill()

    df["mesic"] = df["cas"].dt.strftime("%Y-%m")
    df["den"] = df["cas"].dt.strftime("%Y-%m-%d")
    return df


# --- STAV NAVIGACE ---
if "level" not in st.session_state:
    st.session_state.level = "mesice"
    st.session_state.vybrany_mesic = None
    st.session_state.vybrany_den = None

# --- BOČNÍ PANEL ---
st.sidebar.title("🌡️ Meteostanice")
if st.sidebar.button("🔄 Zkontrolovat nová data"):
    st.cache_data.clear()
    st.rerun()

try:
    df = load_data(URL_TVOJE_TABULKY)
    posledni = df.iloc[-1]
    st.sidebar.success(f"Poslední měření:\n{posledni['cas'].strftime('%d.%m.%Y %H:%M')}")
    st.sidebar.metric("Poslední teplota uvnitř", f"{posledni['temp_in']} °C")
    st.sidebar.metric("Poslední teplota venku", f"{posledni['temp_out']} °C")
    st.sidebar.caption(f"Tlak: {posledni['press_in']} hPa | Vlhkost: {posledni['hum_in']}%")
except Exception as e:
    st.error(f"Chyba při načítání: {e}")
    st.stop()


# =========================================================
# 1. ÚROVEŇ: GRAF MĚSÍCŮ
# =========================================================
if st.session_state.level == "mesice":
    st.title("📊 Přehled měsíců (Průměrné teploty)")
    st.caption("Klikni přímo do grafu na sloupec měsíce (nebo na tlačítko pod grafem) pro rozkliknutí dnů:")

    # Spočítáme průměry za měsíce
    mesicni = df.groupby("mesic").agg({
        "temp_in": "mean",
        "temp_out": "mean",
        "hum_in": "mean",
        "hum_out": "mean",
        "press_in": "mean",
        "press_out": "mean"
    }).round(1).reset_index().sort_values("mesic")

    # Sloupcový graf měsíců
    fig_m = go.Figure()
    fig_m.add_trace(go.Bar(
        x=mesicni["mesic"],
        y=mesicni["temp_in"],
        name="Uvnitř (°C)",
        text=mesicni["temp_in"].apply(lambda x: f"{x} °C"),
        textposition="auto",
        marker_color="#E64A19"
    ))
    fig_m.add_trace(go.Bar(
        x=mesicni["mesic"],
        y=mesicni["temp_out"],
        name="Venku (°C)",
        text=mesicni["temp_out"].apply(lambda x: f"{x} °C"),
        textposition="auto",
        marker_color="#1976D2"
    ))
    fig_m.update_layout(
        barmode="group",
        xaxis_title="Měsíc",
        yaxis_title="Průměrná teplota (°C)",
        hovermode="x unified",
        clickmode="event+select"
    )

    # Zobrazení grafu s detekcí kliknutí
    event_m = st.plotly_chart(fig_m, use_container_width=True, on_select="rerun", key="chart_mesice")
    if event_m and event_m.get("selection") and event_m["selection"].get("points"):
        kliknuty_mesic = event_m["selection"]["points"][0]["x"]
        if kliknuty_mesic in mesicni["mesic"].values:
            st.session_state.vybrany_mesic = kliknuty_mesic
            st.session_state.level = "dny"
            st.rerun()

    # Rychlá tlačítka pod grafem
    st.write("Nebo vyber měsíc tlačítkem:")
    btn_cols = st.columns(max(len(mesicni), 1))
    for i, m_val in enumerate(mesicni["mesic"]):
        with btn_cols[i % len(btn_cols)]:
            if st.button(f"📅 Otevřít měsíc {m_val}", key=f"b_m_{m_val}", use_container_width=True):
                st.session_state.vybrany_mesic = m_val
                st.session_state.level = "dny"
                st.rerun()


# =========================================================
# 2. ÚROVEŇ: GRAF DNŮ VE VYBRANÉM MĚSÍCI
# =========================================================
elif st.session_state.level == "dny":
    mesic = st.session_state.vybrany_mesic

    col_zpet, _ = st.columns([1, 6])
    with col_zpet:
        if st.button("⬅️ Zpět na měsíce", use_container_width=True):
            st.session_state.level = "mesice"
            st.rerun()

    st.title(f"📊 Denní průměry v měsíci {mesic}")
    st.caption("Klikni do grafu na konkrétní den (nebo na tlačítko níže) pro detailní průběh:")

    df_mesic = df[df["mesic"] == mesic]

    # Spočítáme průměry za jednotlivé dny
    denni = df_mesic.groupby("den").agg({
        "temp_in": "mean",
        "temp_out": "mean",
        "hum_in": "mean",
        "hum_out": "mean",
        "press_in": "mean",
        "press_out": "mean"
    }).round(1).reset_index().sort_values("den")

    # Sloupcový graf dnů
    fig_d = go.Figure()
    fig_d.add_trace(go.Bar(
        x=denni["den"],
        y=denni["temp_in"],
        name="Uvnitř (°C)",
        text=denni["temp_in"].apply(lambda x: f"{x}°"),
        textposition="auto",
        marker_color="#E64A19"
    ))
    fig_d.add_trace(go.Bar(
        x=denni["den"],
        y=denni["temp_out"],
        name="Venku (°C)",
        text=denni["temp_out"].apply(lambda x: f"{x}°"),
        textposition="auto",
        marker_color="#1976D2"
    ))
    fig_d.update_layout(
        barmode="group",
        xaxis_title="Den",
        yaxis_title="Průměrná teplota (°C)",
        hovermode="x unified",
        clickmode="event+select"
    )

    # Zobrazení grafu s detekcí kliknutí
    event_d = st.plotly_chart(fig_d, use_container_width=True, on_select="rerun", key="chart_dny")
    if event_d and event_d.get("selection") and event_d["selection"].get("points"):
        kliknuty_den = event_d["selection"]["points"][0]["x"]
        if kliknuty_den in denni["den"].values:
            st.session_state.vybrany_den = kliknuty_den
            st.session_state.level = "detail"
            st.rerun()

    # Rychlá tlačítka dnů pod grafem
    st.write("Nebo vyber den tlačítkem:")
    dny_seznam = denni["den"].tolist()
    dny_cols = st.columns(min(len(dny_seznam), 4))
    for idx, d_val in enumerate(dny_seznam):
        with dny_cols[idx % len(dny_cols)]:
            if st.button(f"📆 {d_val}", key=f"b_d_{d_val}", use_container_width=True):
                st.session_state.vybrany_den = d_val
                st.session_state.level = "detail"
                st.rerun()


# =========================================================
# 3. ÚROVEŇ: DETAIL VYBRANÉHO DNE (ČASOVÉ GRAFY)
# =========================================================
elif st.session_state.level == "detail":
    den = st.session_state.vybrany_den

    col_zpet, _ = st.columns([1, 6])
    with col_zpet:
        if st.button("⬅️ Zpět na dny", use_container_width=True):
            st.session_state.level = "dny"
            st.rerun()

    st.title(f"📈 Detailní průběh dne: {den}")

    den_data = df[df["den"] == den].sort_values("cas")

    # Karty s metrikami
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Teplota Uvnitř (průměr)", f"{den_data['temp_in'].mean():.1f} °C", f"max {den_data['temp_in'].max():.1f} °C")
    kpi2.metric("Teplota Venku (průměr)", f"{den_data['temp_out'].mean():.1f} °C", f"max {den_data['temp_out'].max():.1f} °C")
    kpi3.metric("Vlhkost (Uvnitř / Venku)", f"{den_data['hum_in'].mean():.0f}% / {den_data['hum_out'].mean():.0f}%")
    kpi4.metric("Tlak (Uvnitř / Venku)", f"{den_data['press_in'].mean():.1f} / {den_data['press_out'].mean():.1f} hPa")

    st.divider()

    # 1. Průběh teplot
    st.subheader("🌡️ Průběh teploty v čase")
    fig_temp = go.Figure()
    fig_temp.add_trace(go.Scatter(x=den_data["cas"], y=den_data["temp_in"], mode="lines+markers", name="Uvnitř (°C)", line=dict(color="#E64A19", width=2)))
    fig_temp.add_trace(go.Scatter(x=den_data["cas"], y=den_data["temp_out"], mode="lines+markers", name="Venku (°C)", line=dict(color="#1976D2", width=2)))
    fig_temp.update_layout(xaxis_title="Čas", yaxis_title="Teplota (°C)", hovermode="x unified")
    st.plotly_chart(fig_temp, use_container_width=True)

    # 2. a 3. Grafy vlhkosti a tlaku
    g_col1, g_col2 = st.columns(2)
    with g_col1:
        st.subheader("💧 Průběh vlhkosti (%)")
        fig_hum = go.Figure()
        fig_hum.add_trace(go.Scatter(x=den_data["cas"], y=den_data["hum_in"], mode="lines", name="Uvnitř (%)", line=dict(color="#00ACC1")))
        fig_hum.add_trace(go.Scatter(x=den_data["cas"], y=den_data["hum_out"], mode="lines", name="Venku (%)", line=dict(color="#43A047")))
        fig_hum.update_layout(xaxis_title="Čas", yaxis_title="Vlhkost (%)", hovermode="x unified")
        st.plotly_chart(fig_hum, use_container_width=True)

    with g_col2:
        st.subheader("⏲️ Průběh tlaku (hPa)")
        fig_press = go.Figure()
        fig_press.add_trace(go.Scatter(x=den_data["cas"], y=den_data["press_in"], mode="lines", name="Uvnitř (hPa)", line=dict(color="#FB8C00")))
        fig_press.add_trace(go.Scatter(x=den_data["cas"], y=den_data["press_out"], mode="lines", name="Venku (hPa)", line=dict(color="#8E24AA")))
        fig_press.update_layout(xaxis_title="Čas", yaxis_title="Tlak (hPa)", hovermode="x unified")
        st.plotly_chart(fig_press, use_container_width=True)
