import streamlit as st
import cv2
import socket
import qrcode
import uuid
import numpy as np          
import datetime
import requests
from sqlalchemy import create_engine, Column, String
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------- LOCATION ----------------
def get_location():
    try:
        res = requests.get("https://ipinfo.io/json")
        data = res.json()
        return data.get("city", "Unknown")
    except:
        return "Unknown"

# ---------------- DB ----------------
engine = create_engine("sqlite:///data.db")

Base = declarative_base()

class Product(Base):
    __tablename__ = "products"

    product_id = Column(String(100), primary_key=True)
    farmer_name = Column(String(100))
    location = Column(String(100))
    product_name = Column(String(100))
    trader_name = Column(String(100))
    trader_location = Column(String(100))
    retailer_name = Column(String(100))
    retailer_location = Column(String(100))
    scan_count = Column(String(10))
    last_scan_time = Column(String(50))
    last_location = Column(String(100))

class ScanLog(Base):
    __tablename__ = "scan_logs"

    id = Column(String(100), primary_key=True)
    product_id = Column(String(100))
    role = Column(String(50))
    location = Column(String(100))
    time = Column(String(50))

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)
session = Session()

st.title("🌾 Food Traceability System")

# ---------------- SESSION ----------------
if "product_id" not in st.session_state:
    st.session_state.product_id = None

if "scan_done" not in st.session_state:
    st.session_state.scan_done = False

# ---------------- FARMER ----------------
st.header("👨‍🌾 Farmer Entry")

farmer_name = st.text_input("Farmer Name")
farmer_location = st.text_input("Location")
product_name = st.text_input("Product Name")

if st.button("Generate QR"):
    if farmer_name and farmer_location and product_name:

        product_id = str(uuid.uuid4())

        new_product = Product(
            product_id=product_id,
            farmer_name=farmer_name,
            location=farmer_location,
            product_name=product_name,
            scan_count="0"
        )

        session.add(new_product)
        session.commit()

        hostname = socket.gethostname()
        ip=socket.gethostbyname(hostname)
        url = f"http://{ip}:8501/?id={product_id}"
        qr = qrcode.make(url)
        qr.save("qr.png")

        st.success("QR Generated")
        st.image("qr.png")
        st.write(product_id)

    else:
        st.error("Fill all fields")

# ---------------- URL READ ----------------
query_params = st.query_params
if "id" in query_params:
    st.session_state.product_id = query_params["id"]

# ---------------- QR SCAN ----------------
st.header("📦 Scan QR")

uploaded_file = st.file_uploader("Upload QR", type=["png", "jpg"])

if uploaded_file:
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    image = cv2.imdecode(file_bytes, 1)

    detector = cv2.QRCodeDetector()
    data, _, _ = detector.detectAndDecode(image)

    if data:
        if "id=" in data:
            st.session_state.product_id = data.split("id=")[-1]
        else:
            st.session_state.product_id = data

        st.session_state.scan_done = False
        st.success("QR Scanned")

# ---------------- MAIN LOGIC ----------------
if st.session_state.product_id:

    product = session.query(Product).filter_by(
        product_id=st.session_state.product_id
    ).first()

    if product:

        location = get_location()
        now = datetime.datetime.now()

        # -------- ROLE DETECT --------
        if not product.trader_name:
            role = "trader"
        elif not product.retailer_name:
            role = "retailer"
        else:
            role = "customer"

        # -------- SCAN LOG --------
        if not st.session_state.scan_done:
            log = ScanLog(
                id=str(uuid.uuid4()),
                product_id=product.product_id,
                role=role,
                location=location,
                time=now.isoformat()
            )
            session.add(log)

            product.scan_count = str(int(product.scan_count or "0") + 1)
            st.session_state.scan_done = True

        # -------- FRAUD LOGIC --------
        suspicious = False
        warning = False
        info_flag=False

        if product.last_scan_time and product.last_location:
            try:
                last_time = datetime.datetime.fromisoformat(product.last_scan_time)
                time_diff = (now - last_time).total_seconds()

                if role!="customer" and location != product.last_location:
                    
                    if role=="trader":
                        if time_diff<30:
                            suspicious=True
                        elif time_diff<180:
                            warning=True

                    elif role=="retailer":
                        if time_diff<30:
                            suspicious=True
                        elif time_diff<120:
                            warning=True
                        elif time_diff<300:
                            info_flag=True


            except:
                pass

        product.last_scan_time = now.isoformat()
        product.last_location = location

        session.commit()

        # -------- ALERT --------
        if suspicious:
            st.error("🚨 Fraud Detected")
        elif warning:
            st.warning(f"⚠️ Suspicious movement detected, Location changed within {int(time_diff)} sec")
        elif info_flag:
            st.info(f"ℹ️ Location changed after {int(time_diff)} sec")


        # -------- DISPLAY --------
        st.write("👨‍🌾 Farmer:", product.farmer_name)
        st.write("🌾 Product:", product.product_name)
        st.write("📍 Your Location:", location)

        if product.trader_name:
            st.write("🚚 Trader:", product.trader_name)

        if product.retailer_name:
            st.write("🏪 Retailer:", product.retailer_name)


        # -------- TRADER --------
        if not product.trader_name:
            trader_name = st.text_input("Trader Name")

            if st.button("Add Trader"):
                product.trader_name = trader_name
                product.trader_location = location
                session.commit()
                st.success("Trader added")

        # -------- RETAILER --------
        elif not product.retailer_name:
            retailer_name = st.text_input("Retailer Name")

            if st.button("Add Retailer"):
                product.retailer_name = retailer_name
                product.retailer_location = location
                session.commit()
                st.success("Retailer added")

        # -------- FINAL --------
        else:
            st.success("🏁 Supply Chain Completed")

    else:
        st.error("Product not found ❌")

else:
    st.info("📌 Scan QR first")
