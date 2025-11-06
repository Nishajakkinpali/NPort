from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import requests
import xml.etree.ElementTree as ET

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# SEC need name and email
SEC_HEADERS = {
    "User-Agent": "Nisha Jakkinpali njakkinpali@gmail.com",
    "Accept-Encoding": "gzip, deflate",
    "Accept": "application/json,text/html,*/*",
}

# wrapper
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def _sec_get(url: str, timeout=30) -> requests.Response:
    resp = requests.get(url, headers=SEC_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp
# file html or xml
def _is_html(blob: bytes) -> bool:
    head = blob[:800].lower().strip()
    return head.startswith(b"<!doctype html") or b"<html" in head

def _xml_root_or_none(blob: bytes):
    try:
        return ET.fromstring(blob)
    except Exception:
        return None

def _tag_name(el) -> str:
    return el.tag.split("}")[-1].lower()

# ---------------------------
# Core API
# ---------------------------
@app.get("/api/holdings")
def get_holdings(cik: str):
    # error handling for CIK number
    if not cik.isdigit() or len(cik) > 10:
        raise HTTPException(status_code=400, detail="Invalid CIK format. Use up to 10 digits.")
    # makes cik 10 digits
    cik_padded = cik.zfill(10)
    cik_no_zeros = str(int(cik_padded)) 

    # Go into SEC’s database, get data from companies with this CIK num
    subs_url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        subs = _sec_get(subs_url, timeout=45).json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"SEC submissions fetch failed: {e}")
    # pull type of filing, id, and file name from recent
    recent = subs.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accession = recent.get("accessionNumber", [])
    primary_doc = recent.get("primaryDocument", [])
    if not forms:
        raise HTTPException(status_code=404, detail="No filings listed for this CIK.")

    # Scan from newest to oldest, find first NPORT 
    idx = None
    for i, f in enumerate(forms):
        if f and f.upper().startswith("NPORT"):
            idx = i
            break
    if idx is None:
        raise HTTPException(status_code=404, detail="No recent N-PORT filings found for this CIK.")

    acc_nodash = accession[idx].replace("-", "")
    primary = primary_doc[idx]  

    # Build the base directory of the filing
    base_dir = f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{acc_nodash}"

    # holds all possible XML files
    candidates = []
    try:
        primary_url = f"{base_dir}/{primary}"
        r = _sec_get(primary_url, timeout=45)
        if not _is_html(r.content):
            root = _xml_root_or_none(r.content)
            if root is not None:
                candidates.append(("primary", root, r.content))
    except Exception:
        pass  # keep going

    # If no valid XML, list the directory and try other XML files
    if not candidates:
        idx_url = f"{base_dir}/index.json"
        try:
            listing = _sec_get(idx_url, timeout=45).json()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not list filing folder: {e}")

        # Get the list of all items in the filing folder
        directory = listing.get("directory", {})
        items = directory.get("item", [])

        # Extract just the filenames from the list of items
        all_files = []
        for file_info in items:
            name = file_info.get("name")
            if name:
                all_files.append(name)

        # Keep only the files that end with ".xml"
        xml_files = []
        for name in all_files:
            if name.lower().endswith(".xml"):
                xml_files.append(name)
        # Priority order
        priority_order = ["formnportp.xml", "formnport.xml", "primary_doc.xml"]
        ordered = []

        # Add priority files first
        for name in priority_order:
            if name in xml_files:
                ordered.append(name)

        # Then add any remaining .xml files
        for name in xml_files:
            if name not in ordered:
                ordered.append(name)

        for fname in ordered:
            try:
                url = f"{base_dir}/{fname}"
                rr = _sec_get(url, timeout=45)
                if _is_html(rr.content):
                    continue
                root = _xml_root_or_none(rr.content)
                if root is not None:
                    candidates.append((fname, root, rr.content))
                    break
            except Exception:
                continue

    if not candidates:
        raise HTTPException(status_code=500, detail="Could not locate a parsable XML in this filing.")

    # take first successful candidate
    _, root, _ = candidates[0]

    # extract holdings
    rows = []
    for elem in root.iter():
        child = { _tag_name(c): (c.text or "").strip() for c in list(elem) }

        title = child.get("name") or child.get("title") or child.get("securityname") or ""
        value = child.get("value") or child.get("valusd") or child.get("fairvalue") or ""
        if title and value:
            rows.append({
                "cusip": child.get("cusip") or child.get("idcusip") or "",
                "title": title,
                "balance": child.get("balance") or child.get("shares") or child.get("amount") or "",
                "value": value
            })

    if not rows:
        raise HTTPException(status_code=404, detail="No holdings found in the latest filing.")

    # remove duplicates
    seen = set()
    uniq = []
    for r in rows:
        key = (r["cusip"], r["title"], r["balance"], r["value"])
        if key not in seen:
            seen.add(key)
            uniq.append(r)

    return {"cik": cik_padded, "count": len(uniq), "holdings": uniq[:2000]}
