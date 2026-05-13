#!/usr/bin/env python3
"""
Hero MotoCorp Dealer Website Scraper
Scrapes all data from a dealer page and generates dealer JSON + website files.

Usage:
    python scraper.py --url "https://dealers.heromotocorp.com/..." --folder "dhansri-motors"

GitHub Actions passes these as environment variables:
    DEALER_URL, DEALER_FOLDER
"""

import os
import json
import re
import time
import argparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
HERO_CDN = "https://d2ki7eiqd260sq.cloudfront.net"

PRODUCT_SPECS_KNOWN = {
    "XTREME 160R 4V":  {"cc": "163.2cc", "features": ["First in Segment New Panic Brake Alert", "Max Power 16.9 Ps @ 8500 rpm", "12L Fuel Tank", "LED Headlamp"]},
    "XTREME 160R":     {"cc": "163.2cc", "features": ["First in Segment Drag Timer", "Max Power 15 Ps @ 8500 rpm", "12L Fuel Tank", "LED Headlamp"]},
    "XTREME 125R":     {"cc": "125cc",   "features": ["Sprint City Riding", "ABS", "LED Headlamps", "Digital Console"]},
    "XPULSE 200 4V":   {"cc": "199.6cc", "features": ["Adjustable Front and Rear Suspension", "Max Power 18.9 BHP @ 8500 rpm", "13L Fuel Tank", "Adventure Ready"]},
    "XPULSE 200":      {"cc": "199.6cc", "features": ["Adventure Touring", "Max Power 18.4 BHP", "13L Fuel Tank"]},
    "HF 100":          {"cc": "97.2cc",  "features": ["xSESN FI Technology", "High Mileage", "9.1L Fuel Tank", "i3S Start-Stop"]},
    "SPLENDOR+ XTEC":  {"cc": "97.2cc",  "features": ["Bluetooth Connectivity", "Digital Console", "i3S Technology", "LED DRL"]},
    "SPLENDOR+":       {"cc": "97.2cc",  "features": ["Reliable Performance", "Excellent Mileage", "Alloy Wheels"]},
    "GLAMOUR X":       {"cc": "124.7cc", "features": ["Cruise Control", "AERA Technology", "10L Fuel Tank", "LED Projector"]},
    "GLAMOUR":         {"cc": "124.7cc", "features": ["Stylish Design", "FI Engine", "10L Fuel Tank"]},
    "DESTINI PRIME":   {"cc": "124.6cc", "features": ["i3S Technology", "5L Fuel Tank", "9 BHP Power", "Alloy Wheels"]},
    "XOOM 125":        {"cc": "124.6cc", "features": ["Cornering Lamps", "Wide Tires", "USB Charging", "LED Lights"]},
    "XOOM":            {"cc": "110cc",   "features": ["Smart Connect", "Wide Tires", "LED Lights"]},
    "PLEASURE+ XTEC":  {"cc": "110cc",   "features": ["LED Projector Lamp", "Chrome Finish", "Bluetooth", "i3S"]},
    "PASSION XTEC":    {"cc": "113cc",   "features": ["Connected Features", "5-Step Adjustable Suspension", "LED DRL"]},
    "KARIZMA XMR":     {"cc": "210cc",   "features": ["Dual Channel ABS", "Assist and Slipper Clutch", "14L Fuel Tank", "Max Power 25.5 PS"]},
    "MAVRICK 440":     {"cc": "440cc",   "features": ["Liquid Cooled Engine", "Dual Channel ABS", "15L Fuel Tank", "Max Power 27 PS"]},
}

def get_driver():
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,900")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    return driver


def wait_for_page(driver, timeout=12):
    """Wait for JS to render content."""
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    time.sleep(4)


def extract_json_ld(driver):
    """Extract JSON-LD structured data from page."""
    scripts = driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
    for script in scripts:
        try:
            data = json.loads(script.get_attribute("innerHTML"))
            if isinstance(data, dict) and data.get("@type") in ["MotorcycleDealer", "AutoDealer", "Store", "LocalBusiness"]:
                return data
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and "name" in item:
                        return item
        except Exception:
            continue
    return {}


def extract_home_data(driver, base_url):
    """Scrape Home page data."""
    driver.get(base_url + "/Home")
    wait_for_page(driver)

    data = {}
    soup = BeautifulSoup(driver.page_source, "html.parser")
    page_text = driver.page_source

    # JSON-LD structured data
    ld = extract_json_ld(driver)
    if ld:
        data["structured"] = ld

    # Dealer name
    try:
        h1 = soup.find("h1")
        if h1:
            data["name"] = h1.get_text(strip=True)
    except Exception:
        pass

    # Try meta OG title
    if not data.get("name"):
        og = soup.find("meta", property="og:title")
        if og:
            data["name"] = og.get("content", "").split("|")[0].strip()

    # Address extraction via regex patterns
    address_patterns = [
        r'(?:H\s*\d+[A-Z,\s]+(?:Sector\s*\d+|[\w\s,]+)(?:Noida|Delhi|Mumbai|[\w\s]+)\s*-?\s*\d{6})',
        r'(\d+[,\s]+[\w\s,]+,\s*[\w\s]+,\s*[\w\s]+\s*-\s*\d{6})',
    ]
    for pat in address_patterns:
        m = re.search(pat, page_text, re.IGNORECASE)
        if m:
            data["address"] = m.group(0).strip()
            break

    # Phone numbers
    phones = list(set(re.findall(r'\b(?:\+91[-\s]?)?[6-9]\d{9}\b', page_text)))
    phones = [p.replace(" ", "").replace("-", "") for p in phones if len(re.sub(r'\D', '', p)) == 10]
    data["phones"] = phones[:3]

    # Email
    emails = re.findall(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', page_text)
    emails = [e for e in emails if "heromotocorp" not in e.lower() and "@" in e]
    if emails:
        data["email"] = emails[0]

    # Timings
    timing_match = re.search(
        r'(\d{2}:\d{2}\s*(?:AM|PM)\s*[-–]\s*\d{2}:\d{2}\s*(?:AM|PM))',
        page_text, re.IGNORECASE
    )
    if timing_match:
        data["timings"] = timing_match.group(1).strip()

    # Rating
    rating_match = re.search(r'(\d+\.\d+)\s*/\s*5', page_text)
    if rating_match:
        data["rating"] = rating_match.group(1)

    review_match = re.search(r'([\d,]+)\s+reviews?', page_text, re.IGNORECASE)
    if review_match:
        data["review_count"] = review_match.group(1).replace(",", "")

    # Payment modes
    payment_modes = []
    mode_keywords = ["Cash", "Master Card", "Debit Card", "Visa", "Credit Card", "QR Scan", "Bhim UPI", "UPI", "Net Banking"]
    for mode in mode_keywords:
        if mode.lower() in page_text.lower():
            payment_modes.append(mode)
    data["payment_modes"] = payment_modes

    # Google Maps link
    maps_match = re.search(r'https://maps\.google\.com[^\s"\'<>]+', page_text)
    if maps_match:
        data["maps_url"] = maps_match.group(0)

    # Place ID (for Google Reviews)
    place_id_match = re.search(r'placeid=([A-Za-z0-9_\-]+)', page_text)
    if place_id_match:
        data["google_place_id"] = place_id_match.group(1)

    return data


def extract_about_data(driver, base_url):
    """Scrape About page data."""
    driver.get(base_url + "/About")
    wait_for_page(driver)

    page_text = driver.page_source
    soup = BeautifulSoup(page_text, "html.parser")

    about = {}

    # About text
    about_keywords = ["welcome", "mission", "dedicated", "passionate", "expert", "services", "quality"]
    paragraphs = soup.find_all("p")
    about_texts = []
    for p in paragraphs:
        txt = p.get_text(strip=True)
        if len(txt) > 40 and any(kw in txt.lower() for kw in about_keywords):
            about_texts.append(txt)
    if about_texts:
        about["description"] = " ".join(about_texts[:3])

    # Services
    services = []
    service_keywords = ["Sales", "Service", "Exchange", "Financing", "Spare Parts", "Insurance", "Test Drive", "Parking"]
    for kw in service_keywords:
        if kw.lower() in page_text.lower():
            services.append(kw)
    about["services"] = services

    return about


def extract_products_data(driver, base_url):
    """Scrape Products page data."""
    driver.get(base_url + "/Products")
    wait_for_page(driver)

    page_text = driver.page_source
    soup = BeautifulSoup(page_text, "html.parser")

    products = []
    seen_names = set()

    # Extract product names from headings
    for tag in soup.find_all(["h2", "h3", "h4", "strong"]):
        name = tag.get_text(strip=True).upper()
        for known_name in PRODUCT_SPECS_KNOWN:
            if known_name.upper() in name and known_name not in seen_names:
                seen_names.add(known_name)
                spec = PRODUCT_SPECS_KNOWN[known_name]

                # Find nearby image
                img_url = None
                parent = tag.find_parent()
                if parent:
                    img = parent.find("img")
                    if img:
                        src = img.get("src") or img.get("data-src") or ""
                        if src and ("cloudfront" in src or "heromotocorp" in src or "cdn" in src):
                            img_url = src

                # Search in full HTML for image with product slug
                if not img_url:
                    slug = known_name.lower().replace(" ", "-").replace("+", "-plus")
                    img_pattern = rf'https://[^"\'<>\s]*cloudfront\.net/[^"\'<>\s]*{re.escape(slug)}[^"\'<>\s]*\.(?:png|jpg|webp)'
                    img_match = re.search(img_pattern, page_text, re.IGNORECASE)
                    if img_match:
                        img_url = img_match.group(0)

                products.append({
                    "name": known_name,
                    "cc": spec["cc"],
                    "features": spec["features"],
                    "image": img_url or f"{HERO_CDN}/{known_name.lower().replace(' ', '-')}.png"
                })

    # Fallback: extract all cloudfront images with product patterns
    all_imgs = re.findall(r'https://d2ki7eiqd260sq\.cloudfront\.net/[^"\'<>\s]+\.(?:png|jpg|webp)', page_text)
    img_map = {}
    for img in all_imgs:
        fname = img.split("/")[-1].split(".")[0].lower()
        for known_name in PRODUCT_SPECS_KNOWN:
            slug = known_name.lower().replace(" ", "-").replace("+", "-").replace("4v", "4v")
            if slug in fname or fname in slug:
                img_map[known_name] = img

    # Update products with better images
    for p in products:
        if p["name"] in img_map and not p["image"].startswith(HERO_CDN + "/" + p["name"]):
            pass  # already found
        elif p["name"] in img_map:
            p["image"] = img_map[p["name"]]

    return products


def extract_gallery_data(driver, base_url):
    """Scrape Gallery page images."""
    driver.get(base_url + "/Gallery")
    wait_for_page(driver)

    page_text = driver.page_source

    # All cloudfront images
    images = list(set(re.findall(
        r'https://d2ki7eiqd260sq\.cloudfront\.net/[^"\'<>\s]+\.(?:jpg|jpeg|png|webp)',
        page_text
    )))

    # Filter out product images (those are usually smaller/specific)
    gallery_imgs = [img for img in images if not any(
        p.lower().replace(" ", "-") in img.lower()
        for p in PRODUCT_SPECS_KNOWN
    )]

    return gallery_imgs[:20]  # Max 20 gallery images


def build_dealer_json(folder, dealer_url):
    """Main function to scrape and build dealer data JSON."""
    print(f"[INFO] Starting scrape for: {dealer_url}")
    print(f"[INFO] Folder: {folder}")

    base_url = dealer_url.rstrip("/").rsplit("/", 1)[0]
    if base_url.endswith("/Home") or base_url.endswith("/About"):
        base_url = base_url.rsplit("/", 1)[0]

    driver = get_driver()

    try:
        home_data = extract_home_data(driver, base_url)
        about_data = extract_about_data(driver, base_url)
        products = extract_products_data(driver, base_url)
        gallery = extract_gallery_data(driver, base_url)
    finally:
        driver.quit()

    # Build final JSON
    dealer = {
        "folder": folder,
        "source_url": dealer_url,
        "name": home_data.get("name", "Hero MotoCorp Dealer"),
        "tagline": "Your Trusted Hero MotoCorp Dealership",
        "address": home_data.get("address", ""),
        "phones": home_data.get("phones", []),
        "email": home_data.get("email", ""),
        "whatsapp": home_data.get("phones", [""])[0] if home_data.get("phones") else "",
        "timings": home_data.get("timings", "09:00 AM - 08:30 PM"),
        "timings_days": "Monday - Sunday",
        "rating": home_data.get("rating", "4.5"),
        "review_count": home_data.get("review_count", "500"),
        "google_place_id": home_data.get("google_place_id", ""),
        "maps_url": home_data.get("maps_url", ""),
        "payment_modes": home_data.get("payment_modes", ["Cash", "UPI", "Card"]),
        "services": about_data.get("services", ["Sales", "Service", "Exchange", "Financing"]),
        "about": about_data.get("description", "Welcome to our Hero MotoCorp dealership. We are dedicated to providing the best bikes and scooters to our customers with exceptional service."),
        "products": products,
        "gallery": gallery,
        "notice": {
            "enabled": False,
            "title": "Special Offer!",
            "text": "Get exciting exchange bonus this month. Visit us today!",
            "cta_text": "Book a Test Ride",
            "cta_phone": home_data.get("phones", [""])[0] if home_data.get("phones") else ""
        },
        "seo": {
            "title": f"{home_data.get('name', 'Hero MotoCorp Dealer')} | Official Showroom",
            "description": f"Visit {home_data.get('name', 'our showroom')} for the best Hero MotoCorp bikes and scooters. {about_data.get('description', '')[:100]}",
            "keywords": "Hero MotoCorp, bike dealer, two wheeler, scooter, showroom"
        }
    }

    return dealer


def main():
    parser = argparse.ArgumentParser(description="Hero MotoCorp Dealer Scraper")
    parser.add_argument("--url", required=True, help="Dealer page URL")
    parser.add_argument("--folder", required=True, help="Output folder name")
    parser.add_argument("--output-dir", default="dealers", help="Base output directory")
    args = parser.parse_args()

    # Override with env vars if set (for GitHub Actions)
    url = os.environ.get("DEALER_URL", args.url)
    folder = os.environ.get("DEALER_FOLDER", args.folder)
    output_dir = args.output_dir

    dealer_data = build_dealer_json(folder, url)

    # Write data.json
    out_path = os.path.join(output_dir, folder)
    os.makedirs(out_path, exist_ok=True)

    data_file = os.path.join(out_path, "data.json")
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(dealer_data, f, indent=2, ensure_ascii=False)
    print(f"[SUCCESS] data.json written to: {data_file}")

    # Write notice.json separately (editable by dealer)
    notice_file = os.path.join(out_path, "notice.json")
    if not os.path.exists(notice_file):
        with open(notice_file, "w", encoding="utf-8") as f:
            json.dump(dealer_data["notice"], f, indent=2, ensure_ascii=False)
        print(f"[SUCCESS] notice.json written to: {notice_file}")

    # Copy template HTML
    import shutil
    template_src = os.path.join("_template", "index.html")
    template_dst = os.path.join(out_path, "index.html")
    if os.path.exists(template_src) and not os.path.exists(template_dst):
        shutil.copy(template_src, template_dst)
        print(f"[SUCCESS] index.html copied to: {template_dst}")

    admin_src = os.path.join("_template", "admin.html")
    admin_dst = os.path.join(out_path, "admin.html")
    if os.path.exists(admin_src) and not os.path.exists(admin_dst):
        shutil.copy(admin_src, admin_dst)
        print(f"[SUCCESS] admin.html copied to: {admin_dst}")

    # Generate and write secret password for Admin Panel
    import string
    import random
    secret_file = os.path.join(out_path, "secret.json")
    if not os.path.exists(secret_file):
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
        with open(secret_file, "w", encoding="utf-8") as f:
            json.dump({"password": password}, f, indent=2)
        print(f"[SUCCESS] secret.json written to: {secret_file} (Password: {password})")

    print(f"\n[DONE] Dealer '{folder}' setup complete!")
    print(f"  Files: {out_path}/")
    print("    - data.json")
    print("    - notice.json")
    print("    - index.html")
    print("    - admin.html")
    print("    - secret.json (Admin Password)")


if __name__ == "__main__":
    main()
