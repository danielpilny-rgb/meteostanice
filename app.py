import re
from io import StringIO
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# =====================================================================
# TVŮJ ODKAZ NA GOOGLE TABULKU:
# =====================================================================
URL_TVOJE_TABULKY = "SEM_VLOZ_ODKAZ_NA_TABULKU"

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
        raise ValueError(f"Google vrátil chybu {res.status_code}. Zkontroluj sdílení.")

    if "<html" in res.text.lower():
        raise ValueError("Google poslal přihlašovací stránku. Zkontroluj sdílení.")

    # 1. Načtení dat
    df = pd.read_csv(StringIO(res.text), header=None, sep=None, engine="python")

    # 2. Odstranění prázdných sloupců
    df = df.dropna(how="all", axis=1)

    # 3. Přesně 7 sloupců
    if df.shape[1] > 7:
        df = df.iloc[:, :7]
    elif df.shape[1] < 7:
        raise ValueError(f"Tabulka má jen {df.shape[1]} sloupců, očekává se 7.")

    df.columns = [
        "cas",
        "temp_in",
        "hum_in",
        "press_in",
        "temp_out",
        "hum_out",
        "press_out",
    ]

    # 4. Převod času a zahození záhlaví
    df["cas"] = pd.to_datetime(df["cas"], errors="coerce")
    df = df.dropna(subset=["cas"])

    if df.empty:
        raise ValueError("V datech se nenašel žádný platný datum a čas.")

    # 5. Převod na čísla (čárky na tečky)
    numeric_cols = [
        "temp_in",
        "hum_in",
        "press_in",
        "temp_out",
        "hum_out",
        "press_out",
    ]
    for col in numeric_cols:
        df[col] = df[col].astype(str).str.replace(",", ".").str.strip()
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Seřadíme podle času od nejstaršího po nejnovější
    df = df.sort_values("cas").reset_index(drop=True)

    # -------------------------------------------------------------
    # 6. OŠETŘENÍ VÝPADKŮ OPEN-METEO (NULY):
    # Falešné 0 nahradíme předchozí platnou hodnotou (ffill)
    # -------------------------------------------------------------
    # Venkovní tlak 0 je jasná chyba:
    df["press_out"] = df["press_out"].replace(0, None).ffill()
    # Venkovní vlhkost 0 je taky nesmysl:
    df["hum_out"] = df["hum_out"].replace(0, None).ffill()
    # Venkovní teplota 0 (výpadek API):
    df["temp_out"] = df["temp_out"].replace(0, None).ffill()

    # Pomocné sloupce
    df["mesic"] = df["cas"].dt.strftime("%Y-%m")
    df["den"] = df["cas"].dt.strftime("%Y-%m-%d")

    return df


# --- STAV STRÁNEK ---
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

    posledni_zaznam = df.iloc[-1]
    st.sidebar.success(
        f"Poslední měření:\n{posledni_zaznam['cas'].strftime('%d.%m.%Y %H:%M')}"
    )
    st.sidebar.metric(
        "Poslední teplota uvnitř", f"{posledni_zaznam['temp_in']} °C"
    )
    st.sidebar.metric(
        "Poslední teplota venku", f"{posledni_zaznam['temp_out']} °C"
    )
except Exception as e:
    st.error(f"Chyba při načítání dat: {e}")
    st.stop()


# 1. OBRAZOVKA: MĚSÍCE
if st.session_state.level == "mesice":
    st.title("🗓️ Historie měření – Měsíce")
    st.write("Klikni na měsíc pro výběr jednotlivých dnů:")

    mesicni_staty = (
        df.groupby("mesic")
        .agg(
            {
                "temp_in": "mean",
                "hum_in": "mean",
                "press_in": "mean",
                "temp_out": "mean",
                "hum_out": "mean",
                "press_out": "mean",
            }
        )
        .round(1)
        .sort_index(ascending=False)
    )

    cols_layout = st.columns(3)
    for idx, (mesic, row) in enumerate(mesicni_staty.iterrows()):
        with cols_layout[idx % 3]:
            with st.container(border=True):
                st.subheader(f"📅 Měsíc {mesic}")
                st.write(
                    f"🏠 **Uvnitř:** {row['temp_in']} °C | {row['hum_in']} % | {row['press_in']} hPa"
                )
                st.write(
                    f"🌲 **Venku:** {row['temp_out']} °C | {row['hum_out']} % | {row['press_out']} hPa"
                )

                if st.button(f"Otevřít dny v {mesic}", key=f"btn_{mesic}"):
                    st.session_state.vybrany_mesic = mesic
                    st.session_state.level = "dny"
                    st.rerun()

# 2. OBRAZOVKA: DNY
elif st.session_state.level == "dny":
    mesic = st.session_state.vybrany_mesic

    if st.button("⬅️ Zpět na výběr měsíců"):
        st.session_state.level = "mesice"
        st.rerun()

    st.title(f"📅 Přehled dnů – {mesic}")
    st.write("Klikni na konkrétní den pro zobrazení detailního grafu:")

    df_mesic = df[df["mesic"] == mesic]

    denni_staty = (
        df_mesic.groupby("den")
        .agg(
            {
                "temp_in": ["mean", "min", "max"],
                "hum_in": "mean",
                "press_in": "mean",
                "temp_out": ["mean", "min", "max"],
                "hum_out": "mean",
                "press_out": "mean",
            }
        )
        .round(1)
        .sort_index(ascending=False)
    )

    cols_layout = st.columns(3)
    for idx, (den, row) in enumerate(denni_staty.iterrows()):
        with cols_layout[idx % 3]:
            with st.container(border=True):
                st.subheader(f"📆 {den}")
                st.write(
                    f"🏠 **Uvnitř:** průměr **{row[('temp_in', 'mean')]} °C** (min {row[('temp_in', 'min')]}° / max {row[('temp_in', 'max')]}°)"
                )
                st.write(
                    f"🌲 **Venku:** průměr **{row[('temp_out', 'mean')]} °C** (min {row[('temp_out', 'min')]}° / max {row[('temp_out', 'max')]}°)"
                )
                st.caption(
                    f"💧 Vlhkost: {row[('hum_in', 'mean')]}% / {row[('hum_out', 'mean')]}% | ⏲️ Tlak: {row[('press_in', 'mean')]} hPa"
                )

                if st.button(f"Zobrazit graf dne {den}", key=f"btn_den_{den}"):
                    st.session_state.vybrany_den = den
                    st.session_state.level = "detail"
                    st.rerun()

# 3. OBRAZOVKA: DETAIL S GRAFY
elif st.session_state.level == "detail":
    den = st.session_state.vybrany_den

    if st.button("⬅️ Zpět na dny"):
        st.session_state.level = "dny"
        st.rerun()

    st.title(f"📈 Průběh dne: {den}")

    den_data = df[df["den"] == den].sort_values("cas")

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric(
        "Teplota Uvnitř (průměr)",
        f"{den_data['temp_in'].mean():.1f} °C",
        f"max {den_data['temp_in'].max():.1f} °C",
    )
    kpi2.metric(
        "Teplota Venku (průměr)",
        f"{den_data['temp_out'].mean():.1f} °C",
        f"max {den_data['temp_out'].max():.1f} °C",
    )
    kpi3.metric(
        "Vlhkost (Uvnitř / Venku)",
        f"{den_data['hum_in'].mean():.0f}% / {den_data['hum_out'].mean():.0f}%",
    )
    kpi4.metric(
        "Tlak (Uvnitř / Venku)",
        f"{den_data['press_in'].mean():.1f} / {den_data['press_out'].mean():.1f} hPa",
    )

    st.divider()

    st.subheader("🌡️ Průběh teploty v čase")
    fig_temp = go.Figure()
    fig_temp.add_trace(
        go.Scatter(
            x=den_data["cas"],
            y=den_data["temp_in"],
            mode="lines+markers",
            name="Uvnitř (°C)",
            line=dict(color="#E64A19", width=2),
        )
    )
    fig_temp.add_trace(
        go.Scatter(
            x=den_data["cas"],
            y=den_data["temp_out"],
            mode="lines+markers",
            name="Venku (°C)",
            line=dict(color="#1976D2", width=2),
        )
    )
    fig_temp.update_layout(
        xaxis_title="Čas", yaxis_title="Teplota (°C)", hovermode="x unified"
    )
    st.plotly_chart(fig_temp, use_container_width=True)

    g_col1, g_col2 = st.columns(2)

    with g_col1:
        st.subheader("💧 Průběh vlhkosti (%)")
        fig_hum = go.Figure()
        fig_hum.add_trace(
            go.Scatter(
                x=den_data["cas"],
                y=den_data["hum_in"],
                mode="lines",
                name="Uvnitř (%)",
                line=dict(color="#00ACC1"),
            )
        )
        fig_hum.add_trace(
            go.Scatter(
                x=den_data["cas"],
                y=den_data["hum_out"],
                mode="lines",
                name="Venku (%)",
                line=dict(color="#43A047"),
            )
        )
        fig_hum.update_layout(
            xaxis_title="Čas", yaxis_title="Vlhkost (%)", hovermode="x unified"
        )
        st.plotly_chart(fig_hum, use_container_width=True)

    with g_col2:
        st.subheader("⏲️ Průběh tlaku (hPa)")
        fig_press = go.Figure()
        fig_press.add_trace(
            go.Scatter(
                x=den_data["cas"],
                y=den_data["press_in"],
                mode="lines",
                name="Uvnitř (hPa)",
                line=dict(color="#FB8C00"),
            )
        )
        fig_press.add_trace(
            go.Scatter(
                x=den_data["cas"],
                y=den_data["press_out"],
                mode="lines",
                name="Venku (hPa)",
                line=dict(color="#8E24AA"),
            )
        )
        fig_press.update_layout(
            xaxis_title="Čas", yaxis_title="Tlak (hPa)", hovermode="x unified"
        )
        st.plotly_chart(fig_press, use_container_width=True)