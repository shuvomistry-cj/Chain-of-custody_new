import io
import json
from datetime import datetime, timezone
from typing import List, Tuple

import streamlit as st
import streamlit.components.v1 as components
import base64
try:
    import qrcode  # type: ignore
    QR_AVAILABLE = True
except Exception:
    qrcode = None  # type: ignore
    QR_AVAILABLE = False
import requests  # ensure available as per requirements
import streamlit_authenticator as stauth  # imported per requirement (not used for auth storage)

# Optional components: camera and drawable canvas
try:
    from streamlit_camera_input_live import camera_input_live  # type: ignore
    CAM_AVAILABLE = True
except Exception:
    CAM_AVAILABLE = False
    def camera_input_live():  # fallback no-op
        return None

try:
    from streamlit_drawable_canvas import st_canvas  # type: ignore
    CANVAS_AVAILABLE = True
except Exception:
    CANVAS_AVAILABLE = False
    def st_canvas(*args, **kwargs):  # fallback no-op
        return None

from api_client import APIClient


# ------------------------------
# Lightweight styling
# ------------------------------
def apply_base_styles():
    st.markdown(
        """
        <style>
        /* Page padding and background tweaks */
        .main > div { padding-top: 1rem; }
        /* Keep default sidebar background from Streamlit theme */
        .stButton>button {
            border-radius: 8px;
            background: #4f46e5; /* indigo */
            color: #ffffff;
            border: 1px solid #4338ca;
        }
        .stButton>button:hover { background: #4338ca; border-color: #3730a3; }
        .stDownloadButton>button {
            border-radius: 8px;
            background: #10b981; /* emerald */
            color: #ffffff;
            border: 1px solid #059669;
        }
        .stDownloadButton>button:hover { background: #059669; border-color: #047857; }

        /* Card container */
        .coc-card { 
            background: #ffffff; 
            border: 1px solid #e6e6e6; 
            border-radius: 10px; 
            padding: 1rem 1.25rem; 
            box-shadow: 0 1px 2px rgba(0,0,0,0.04);
            margin-left: 6px;
        }
        /* Table-style row box */
        .coc-row-card {
            background: #ffffff;
            border: 1px solid #e5e7eb;
            border-radius: 10px;
            padding: .5rem .75rem;
            margin-bottom: .5rem;
        }
        .coc-chip { font-size: 12px; padding: 2px 8px; border-radius: 999px; display: inline-block; }
        .chip-green { background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; }
        .chip-blue { background:#eff6ff; color:#1e40af; border:1px solid #bfdbfe; }
        .chip-amber { background:#fffbeb; color:#92400e; border:1px solid #fde68a; }
        .chip-red { background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }

        /* Audit card */
        .audit-card { border-left: 4px solid #e5e7eb; }
        .audit-head { display:flex; align-items:center; justify-content:space-between; gap:.5rem; }
        .audit-title { font-weight:600; }
        .audit-sub { color:#6b7280; font-size:12px; }

        /* Sidebar footer pin */
        aside[data-testid="stSidebar"] div[data-testid="stSidebarContent"] { position: relative; min-height: 100%; padding-bottom: 90px; }
        aside[data-testid="stSidebar"] .sidebar-footer { position: absolute; bottom: 12px; left: 12px; right: 12px; font-size: 11px; color:#6b7280; line-height:1.2; }
        aside[data-testid="stSidebar"] .sidebar-footer a { color:#6b7280; text-decoration: none; }
        aside[data-testid="stSidebar"] .sidebar-footer a:hover { text-decoration: underline; }

        /* Page footer for login */
        .page-footer { position: fixed; bottom: 12px; left: 12px; font-size: 12px; color:#6b7280; line-height:1.2; z-index: 999; }
        .page-footer a { color:#6b7280; text-decoration: none; }
        .page-footer a:hover { text-decoration: underline; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ------------------------------
# Helpers
# ------------------------------

def init_state():
    if "api" not in st.session_state:
        st.session_state.api = APIClient()
    if "access_token" not in st.session_state:
        st.session_state.access_token = None
    if "user" not in st.session_state:
        st.session_state.user = None
    if "page" not in st.session_state:
        st.session_state.page = "login"
    if "evidence_id" not in st.session_state:
        st.session_state.evidence_id = None

def _qr_bytes_for_evidence(ev: dict) -> bytes:
    if not QR_AVAILABLE:
        raise RuntimeError("QR code library not installed. Install 'qrcode' and 'Pillow'.")
    data_lines = [
        f"Evidence ID: {ev.get('evidence_id_str')}",
        f"ID: {ev.get('id')}",
        f"Case No: {ev.get('case_no')}",
        f"Item No: {ev.get('item_no')}",
        f"Badge No: {ev.get('badge_no')}",
        f"Custodian: {ev.get('current_custodian_name') or '—'}",
    ]
    payload = "\n".join([s for s in data_lines if s])
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _build_coc_html(ev: dict, audit_entries: list[dict], qr_png: bytes | None) -> str:
    # Prepare values
    agency = ev.get('agency') or ''
    case_no = ev.get('case_no') or ''
    offense = ev.get('offense') or ''
    item_no = ev.get('item_no') or ''
    badge_no = ev.get('badge_no') or ''
    collected = ev.get('collected_at_utc') or ''
    location = ev.get('location') or ''
    evidence_id_str = ev.get('evidence_id_str') or ''
    evidence_name = ev.get('evidence_name') or ''
    custodian = ev.get('current_custodian_name') or ''

    qr_tag = ''
    if qr_png:
        b64 = base64.b64encode(qr_png).decode()
        qr_tag = f"<img src='data:image/png;base64,{b64}' style='width:120px;height:120px' />"

    # Build chain rows: From, To, Action, Date/Time (UTC)
    rows = []
    for e in audit_entries or []:
        meta = e.get('details') if isinstance(e, dict) else None
        from_person = (
            (e.get('from_name') if isinstance(e, dict) else None)
            or (e.get('from_user_name') if isinstance(e, dict) else None)
            or (e.get('from_user') if isinstance(e, dict) else None)
            or (e.get('previous_custodian') if isinstance(e, dict) else None)
            or (e.get('from') if isinstance(e, dict) else None)
            or (meta.get('from_name') if isinstance(meta, dict) else None)
            or (meta.get('from_user_name') if isinstance(meta, dict) else None)
            or (meta.get('previous_custodian') if isinstance(meta, dict) else None)
        )
        to_person = (
            (e.get('to_name') if isinstance(e, dict) else None)
            or (e.get('to_user_name') if isinstance(e, dict) else None)
            or (e.get('to_user') if isinstance(e, dict) else None)
            or (e.get('new_custodian') if isinstance(e, dict) else None)
            or (e.get('to') if isinstance(e, dict) else None)
            or (meta.get('to_name') if isinstance(meta, dict) else None)
            or (meta.get('to_user_name') if isinstance(meta, dict) else None)
            or (meta.get('new_custodian') if isinstance(meta, dict) else None)
        )
        action = (
            (e.get('action') if isinstance(e, dict) else None)
            or (e.get('type') if isinstance(e, dict) else None)
            or (meta.get('action') if isinstance(meta, dict) else None)
        ) or ''
        ts = (
            (e.get('ts_utc') if isinstance(e, dict) else None)
            or (e.get('timestamp') if isinstance(e, dict) else None)
            or (e.get('created_at') if isinstance(e, dict) else None)
            or (meta.get('ts_utc') if isinstance(meta, dict) else None)
        ) or ''
        # Fallbacks
        actor = (e.get('actor_name') if isinstance(e, dict) else None) or (
            f"User #{e.get('actor_user_id')}" if isinstance(e, dict) and e.get('actor_user_id') else None
        )
        if not from_person:
            from_person = actor or ''
        if not to_person:
            to_person = custodian or ''
        rows.append((from_person or '', to_person or '', action, ts))
    # Limit to 20 entries for single page; pad with blanks to show grid lines
    rows = rows[:20]
    while len(rows) < 20:
        rows.append(("", "", "", ""))
    rows_html = "".join([f"<tr><td>{f}</td><td>{t}</td><td>{a}</td><td>{d}</td></tr>" for f, t, a, d in rows])

    html = f"""
    <html>
    <head>
      <meta charset='utf-8'/>
      <title>Chain of Custody Sheet</title>
      <style>
        @page {{ size: A4 portrait; margin: 10mm; }}
        body {{ font-family: Arial, sans-serif; padding: 0; color:#111827; }}
        .sheet {{ width: 190mm; margin: 0 auto; border:1px solid #e5e7eb; padding:8mm; border-radius:6px; }}
        h1 {{ text-align:center; margin: 0 0 6mm; letter-spacing:1px; font-size:18px; }}
        .grid {{ display:grid; grid-template-columns: 1fr 1fr; gap:3mm 8mm; }}
        .row {{ display:flex; gap:8mm; align-items:center; justify-content:space-between; }}
        .label {{ color:#6b7280; font-size:10px; }}
        .val {{ font-weight:600; font-size:12px; }}
        .sec {{ margin-top:4mm; }}
        table {{ width:100%; border-collapse:collapse; margin-top:3mm; }}
        th, td {{ border:1px solid #e5e7eb; padding:2mm 3mm; font-size:10px; }}
        th {{ background:#f9fafb; text-align:left; }}
        .top {{ display:flex; align-items:flex-start; justify-content:space-between; gap:6mm; }}
        .qrbox {{ border:1px dashed #d1d5db; padding:3mm; border-radius:4px; text-align:center; }}
        .muted {{ color:#6b7280; font-size:10px; }}
        .actions {{ margin-top:4mm; text-align:right; }}
      </style>
    </head>
    <body>
      <div class='sheet'>
        <div class='top'>
          <div>
            <h1>Evidence - Chain of Custody</h1>
            <div class='grid'>
              <div><div class='label'>Agency</div><div class='val'>{agency}</div></div>
              <div><div class='label'>Case No</div><div class='val'>{case_no}</div></div>
              <div><div class='label'>Offense</div><div class='val'>{offense}</div></div>
              <div><div class='label'>Item No</div><div class='val'>{item_no}</div></div>
              <div><div class='label'>Badge No</div><div class='val'>{badge_no}</div></div>
              <div><div class='label'>Collected (UTC)</div><div class='val'>{collected}</div></div>
              <div><div class='label'>Location</div><div class='val'>{location}</div></div>
              <div><div class='label'>Custodian</div><div class='val'>{custodian}</div></div>
            </div>
            <div class='sec'>
              <div class='label'>Evidence ID</div>
              <div class='val'>{evidence_id_str}</div>
            </div>
            <div class='sec'>
              <div class='label'>Evidence Name</div>
              <div class='val'>{evidence_name}</div>
            </div>
          </div>
          <div class='qrbox'>
            <div class='muted'>Scan for quick details</div>
            {qr_tag}
          </div>
        </div>

        <div class='sec'>
          <div class='row'>
            <div class='val'>Chain of Custody Log</div>
            <div class='muted'>Auto-generated</div>
          </div>
          <table>
            <thead><tr><th>From (Person)</th><th>To (Person)</th><th>Action</th><th>Date & Time (UTC)</th></tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>
      </div>
      <script>window.onload = function(){{ setTimeout(function(){{ window.focus(); }}, 200); }};</script>
    </body>
    </html>
    """
    return html

def _format_ts(ts: str | None) -> str:
    if not ts:
        return "—"
    # Expecting ISO8601. Show local-like compact format without parsing tz aggressively
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%b %d, %Y %H:%M UTC")
    except Exception:
        return ts

def _action_badge(action: str | None) -> tuple[str, str]:
    a = (action or "").upper()
    if any(k in a for k in ["CREATE", "CREATED"]):
        return ("Created", "chip-green")
    if "TRANSFER" in a:
        return ("Transfer", "chip-blue")
    if "ANALYSIS" in a:
        return ("Analysis", "chip-amber")
    if any(k in a for k in ["DELETE", "REVOKE", "CANCEL"]):
        return ("Warning", "chip-red")
    return (a.title() or "Event", "chip-blue")


def require_login() -> bool:
    if not st.session_state.access_token:
        st.session_state.page = "login"
        st.warning("Please log in to continue.")
        return False
    return True


def set_token(token: str):
    st.session_state.access_token = token
    st.session_state.api.access_token = token


def fetch_me():
    ok, me, err = st.session_state.api.me()
    if ok and me:
        st.session_state.user = me
    else:
        st.error(f"Failed to fetch profile: {err}")


# ------------------------------
# UI Sections
# ------------------------------

def login_page():
    st.title("Chain of Custody - Login")
    # Apply global styles so page footer CSS is available
    apply_base_styles()

    # Minimal login form (we import streamlit_authenticator per requirement but use backend login)
    with st.form("login_form"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        with st.spinner("Signing in..."):
            ok, data, err = st.session_state.api.login(email, password)
        if ok and data and data.get("access_token"):
            set_token(data["access_token"])
            fetch_me()
            st.session_state.page = "dashboard"
            st.success("Logged in successfully.")
            st.rerun()
        else:
            st.error(f"Login failed: {err}")

    # Immutable footer on login page bottom-left
    st.markdown(
        """
        <div class="page-footer">
          <div>Developed and analyzed and Copywrite by</div>
          <div>
            <strong>@Shuvo Mistry</strong> |
            <a href="https://shuvomistry.site" target="_blank" rel="noopener">shuvomistry.site</a> |
            <a href="https://github.com/shuvomistry-cj" target="_blank" rel="noopener">shuvomistry-cj</a>
          </div>
          <div>National Forensic Sciences University | M.Tech 2025 (AIDS)</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sidebar_nav():
    user = st.session_state.user or {}
    role = (user.get("role") or "").upper()

    with st.sidebar:
        st.header("Navigation")
        # Build options without placeholders to avoid duplicate labels
        options = ["Dashboard"]
        if role in ("ANALYST", "COLLECTOR", "ADMIN"):
            options.append("Create Evidence")
        if role == "ADMIN":
            options.append("Admin Panel")
            options.append("User List")
        options.append("Logout")

        # Preserve current page selection in the radio
        current_page = st.session_state.page
        page_to_option = {
            "dashboard": "Dashboard",
            "create": "Create Evidence",
            "admin": "Admin Panel",
            "login": "Dashboard",  # default to Dashboard when logged in
            "evidence_detail": "Dashboard",  # keep sidebar on Dashboard when viewing details
        }
        try:
            current_label = page_to_option.get(current_page, "Dashboard")
            current_index = options.index(current_label)
        except ValueError:
            current_index = 0

        choice = st.radio("Go to", options, index=current_index)

        # Only change page if selection differs from current mapped page
        # Do NOT override when currently on evidence_detail (navigated via buttons)
        if choice == "Dashboard" and current_page not in ("dashboard", "evidence_detail"):
            st.session_state.page = "dashboard"
        elif choice == "Create Evidence" and role in ("ANALYST", "COLLECTOR", "ADMIN") and current_page != "create":
            st.session_state.page = "create"
        elif choice == "Admin Panel" and role == "ADMIN" and current_page != "admin":
            st.session_state.page = "admin"
        elif choice == "User List" and role == "ADMIN" and current_page != "users":
            st.session_state.page = "users"
        elif choice == "Logout":
            st.session_state.page = "login"
            st.session_state.access_token = None
            st.session_state.api.access_token = None
            st.session_state.user = None
            st.session_state.evidence_id = None
            st.rerun()

        st.markdown("---")
        if user:
            st.caption(f"Logged in as: {user.get('name')} ({role})")

        # Immutable signature footer pinned to bottom-left
        st.markdown(
            """
            <div class="sidebar-footer" style="position: fixed; bottom: 0; left: 0; padding: 1rem; font-size: 0.8rem; user-select: none;">
              <div>Developed and analyzed and Copywrite by</div>
              <div>
                <strong>@Shuvo Mistry</strong> |
                <a href="https://shuvomistry.site" target="_blank" rel="noopener" style="text-decoration: none; color: inherit;">shuvomistry.site</a> |
                <a href="https://github.com/shuvomistry-cj" target="_blank" rel="noopener" style="text-decoration: none; color: inherit;">shuvomistry-cj</a>
              </div>
              <div>National Forensic Sciences University | M.Tech 2025 (AIDS)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def dashboard_page():
    if not require_login():
        return

    st.title("Dashboard")
    apply_base_styles()

    # List my custody evidence
    with st.spinner("Loading evidence..."):
        ok, data, err = st.session_state.api.list_evidence(page=1, per_page=50)
    if not ok:
        st.error(f"Failed to fetch evidence: {err}")
        return

    items = data.get("items", []) if isinstance(data, dict) else []

    st.subheader("My Custody Evidence")
    if not items:
        st.info("No evidence found.")
    else:
        # Header row
        h1, h2, h3, h4, h5, h6 = st.columns([5, 3, 2, 2, 2, 2])
        with h1: st.caption("Evidence Name")
        with h2: st.caption("Case No")
        with h3: st.caption("ID")
        with h4: st.caption("")
        with h5: st.caption("")
        with h6: st.caption("")
        # Rows
        for ev in items:
            with st.container():
                # Open row wrapper
                st.markdown("<div class='coc-row-card'>", unsafe_allow_html=True)
                cols = st.columns([5, 3, 2, 2, 2, 2])
                with cols[0]:
                    name = ev.get('evidence_name') or ev.get('evidence_id_str')
                    st.markdown(f"**{name}** <span class='coc-badge'>{ev.get('evidence_id_str')}</span>", unsafe_allow_html=True)
                with cols[1]:
                    st.write(ev.get('case_no'))
                with cols[2]:
                    st.write(str(ev.get('id')))
                with cols[3]:
                    if st.button("View", key=f"view_{ev.get('id')}"):
                        st.session_state.evidence_id = ev.get("id")
                        st.session_state.page = "evidence_detail"
                        st.rerun()
                with cols[4]:
                    if st.button("QR", key=f"qr_{ev.get('id')}"):
                        if not QR_AVAILABLE:
                            st.info("Install 'qrcode' and 'Pillow' to enable QR generation.")
                        else:
                            st.session_state[f"show_qr_{ev.get('id')}"] = not st.session_state.get(f"show_qr_{ev.get('id')}", False)
                with cols[5]:
                    if st.button("CoC Sheet", key=f"coc_{ev.get('id')}"):
                        st.session_state[f"show_coc_{ev.get('id')}"] = not st.session_state.get(f"show_coc_{ev.get('id')}", False)
                # Close row wrapper
                st.markdown("</div>", unsafe_allow_html=True)

                # QR preview section
                show_qr_key = f"show_qr_{ev.get('id')}"
                if QR_AVAILABLE and st.session_state.get(show_qr_key, False):
                    try:
                        qr_png = _qr_bytes_for_evidence(ev)
                        st.caption("QR for printing/scanning")
                        st.image(qr_png, caption=f"{ev.get('evidence_id_str')}", width=200)
                        # Download button
                        st.download_button(
                            label="Download QR",
                            data=qr_png,
                            file_name=f"evidence_{ev.get('id')}_qr.png",
                            mime="image/png",
                            key=f"dl_qr_{ev.get('id')}"
                        )
                        # Print button via HTML window
                        b64 = base64.b64encode(qr_png).decode()
                        html = f"""
                        <html>
                        <head><title>Print QR</title></head>
                        <body style='display:flex;align-items:center;justify-content:center;height:100vh;'>
                          <img id='qr' src='data:image/png;base64,{b64}' style='width:300px;height:300px' />
                          <script>
                            window.onload = function() {{ setTimeout(function(){{ window.print(); }}, 300); }}
                          </script>
                        </body>
                        </html>
                        """
                        if st.button("Print QR", key=f"print_qr_{ev.get('id')}"):
                            components.html(html, height=10)
                    except Exception as e:
                        st.error(f"Failed to generate QR: {e}")

                # CoC sheet section
                show_coc_key = f"show_coc_{ev.get('id')}"
                if st.session_state.get(show_coc_key, False):
                    with st.spinner("Building CoC sheet..."):
                        ok_a, audit_data, audit_err = st.session_state.api.get_audit(int(ev.get('id')))
                    if not ok_a:
                        st.error(f"Failed to load audit: {audit_err}")
                    else:
                        entries = []
                        if isinstance(audit_data, dict):
                            entries = audit_data.get('audit_entries') or audit_data.get('entries') or audit_data.get('items') or []
                        qr_png2 = _qr_bytes_for_evidence(ev) if QR_AVAILABLE else None
                        coc_html = _build_coc_html(ev, entries, qr_png2)
                        # Download HTML
                        st.download_button(
                            label="Download CoC Sheet (HTML)",
                            data=coc_html.encode('utf-8'),
                            file_name=f"evidence_{ev.get('id')}_coc.html",
                            mime="text/html",
                            key=f"dl_coc_{ev.get('id')}"
                        )
                        # Print CoC (open embedded with print)
                        if st.button("Print CoC", key=f"print_coc_{ev.get('id')}"):
                            printable = coc_html.replace('</body>', "<script>setTimeout(()=>window.print(),300);</script></body>")
                            components.html(printable, height=10)

    st.markdown("---")

    # Pending transfers
    st.subheader("My Pending Transfers")
    with st.spinner("Loading pending transfers..."):
        ok, pending, err = st.session_state.api.list_pending_transfers()
    if not ok:
        st.error(f"Failed to fetch pending transfers: {err}")
        return

    if not pending:
        st.info("No pending transfers.")
    else:
        for t in pending:
            cols = st.columns([3, 3, 2, 2])
            with cols[0]:
                st.write(f"Evidence ID: {t.get('evidence_id')} - {t.get('evidence_id_str', '')}")
            with cols[1]:
                st.write(f"From: {t.get('from_user_name')} → To: {t.get('to_user_name')}")
            with cols[2]:
                if st.button("Accept", key=f"acc_{t.get('id')}"):
                    ok, _, err = st.session_state.api.accept_transfer(int(t.get("id")))
                    if ok:
                        st.success("Transfer accepted.")
                        st.rerun()
                    else:
                        st.error(f"Failed: {err}")

    st.markdown("---")
    # Outgoing pending transfers (that I initiated)
    st.subheader("My Outgoing Pending Transfers")
    with st.spinner("Loading outgoing pending transfers..."):
        ok2, outgoing, err2 = st.session_state.api.list_outgoing_pending_transfers()
    if not ok2:
        st.error(f"Failed to fetch outgoing transfers: {err2}")
        return
    if not outgoing:
        st.info("No outgoing pending transfers.")
    else:
        for t in outgoing:
            cols = st.columns([4, 3, 2])
            with cols[0]:
                st.write(f"Evidence ID: {t.get('evidence_id')} - {t.get('evidence_id_str', '')}")
            with cols[1]:
                st.write(f"To: {t.get('to_user_name')}")
            with cols[2]:
                if st.button("Cancel", key=f"cancel_{t.get('id')}"):
                    okc, _, errc = st.session_state.api.cancel_transfer(int(t.get('id')))
                    if okc:
                        st.warning("Transfer cancelled.")
                        st.rerun()
                    else:
                        st.error(f"Failed to cancel: {errc}")


def evidence_detail_page():
    if not require_login():
        return

    eid = st.session_state.evidence_id
    if not eid:
        st.info("No evidence selected.")
        return

    st.title(f"Evidence Detail #{eid}")
    apply_base_styles()

    ok, ev, err = st.session_state.api.get_evidence(eid)
    if not ok or not ev:
        st.error(f"Failed to load evidence: {err}")
        return

    # Fetch audit to show last audit timestamp on the details card
    last_audit_ts = None
    ok_a, audit, _ = st.session_state.api.get_audit(int(eid))
    if ok_a and isinstance(audit, dict):
        entries = audit.get("audit_entries", [])
        if entries:
            # assuming entries have 'ts_utc' sortable timestamps
            try:
                last_audit_ts = max(e.get('ts_utc') for e in entries if e.get('ts_utc'))
            except Exception:
                last_audit_ts = entries[0].get('ts_utc')

    # Card-style metadata
    st.subheader("Details")
    with st.container():
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown(f"**Evidence ID**: {ev.get('evidence_id_str')}")
            st.markdown(f"**Agency**: {ev.get('agency')}")
            # Case number + Add Analysis button (custodian only)
            case_no = ev.get('case_no')
            st.markdown(f"**Case No**: {case_no}")
            if last_audit_ts:
                st.markdown(f"**Last Audit**: {last_audit_ts}")
        with c2:
            st.markdown(f"**Offense**: {ev.get('offense')}")
            st.markdown(f"**Item No**: {ev.get('item_no')}")
            st.markdown(f"**Badge No**: {ev.get('badge_no')}")
        with c3:
            st.markdown(f"**Location**: {ev.get('location')}")
            st.markdown(f"**Collected At (UTC)**: {ev.get('collected_at_utc')}")
            st.markdown(f"**Current Custodian**: {ev.get('current_custodian_name') or '—'}")
    st.markdown("**Description**")
    st.write(ev.get("description", ""))

    # Determine custody
    user = st.session_state.user or {}
    is_custodian = (ev.get('current_custodian_id') == user.get('id'))

    # Add Analysis button (aligned under Case No block)
    if is_custodian:
        if st.button("Add Analysis", key="add_analysis_btn"):
            st.session_state.show_analysis_form = True
    else:
        st.caption("Only the current custodian can add analysis.")

    # Add Analysis form
    if st.session_state.get("show_analysis_form"):
        st.subheader("New Analysis")
        with st.form("analysis_form"):
            today = datetime.now(timezone.utc)
            a_date = st.date_input("Analysis Date", today.date())
            a_time = st.time_input("Analysis Time", today.time())
            analysis_by = st.text_input("Analysis By", user.get("name", ""))
            role = st.text_input("Role", user.get("role", ""))
            place = st.text_input("Place of Analysis", "Lab")
            desc = st.text_area("Description")
            a_files = st.file_uploader("Upload files", type=None, accept_multiple_files=True)
            sub_a = st.form_submit_button("Save Analysis")
        if sub_a:
            at_dt = datetime.combine(a_date, a_time).replace(tzinfo=timezone.utc)
            iso_str = at_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
            files_payload: List[Tuple[str, bytes, str]] = []
            for uf in a_files or []:
                files_payload.append((uf.name, uf.read(), uf.type or "application/octet-stream"))
            with st.spinner("Saving analysis..."):
                ok_ca, res_ca, err_ca = st.session_state.api.create_analysis(
                    evidence_id=int(eid),
                    analysis_at_iso=iso_str,
                    analysis_by=analysis_by,
                    role=role,
                    place_of_analysis=place,
                    description=desc,
                    files=files_payload,
                )
            if ok_ca:
                st.success("Analysis created.")
                st.session_state.show_analysis_form = False
                st.rerun()
            else:
                st.error(f"Failed to create analysis: {err_ca}")

    if st.button("Back to Dashboard", key="back_dash"):
        st.session_state.page = "dashboard"
        st.session_state.evidence_id = None
        st.rerun()

    # Files and download
    st.subheader("Files")
    files = ev.get("files", [])
    if not files:
        st.info("No files.")
    else:
        for f in files:
            fid = f.get("id") or f.get("file_id")
            fname = f.get("orig_filename") or f.get("filename") or "file"
            cols = st.columns([5, 2])
            with cols[0]:
                st.write(f"{fname} (ID: {fid})")
            with cols[1]:
                if fid and st.button("Download", key=f"dl_{fid}"):
                    ok, content, err, dlname = st.session_state.api.download_file(eid, int(fid))
                    if ok and content:
                        st.download_button(
                            label=f"Save {dlname or fname}",
                            data=content,
                            file_name=dlname or fname,
                            mime=f.get("mime") or "application/octet-stream",
                            key=f"save_{fid}"
                        )
                    else:
                        st.error(f"Download failed: {err}")

    # Analyses section
    st.subheader("Analyses")
    ok_an, an_list, an_err = st.session_state.api.list_analyses(int(eid))
    if not ok_an:
        st.error(f"Failed to load analyses: {an_err}")
    else:
        items = (an_list or {}).get("items", [])
        if not items:
            st.info("No analyses yet.")
        else:
            # Buttons: Analysis 1, Analysis 2, ...
            btn_cols = st.columns(min(len(items), 5))
            for idx, a in enumerate(items, start=1):
                col = btn_cols[(idx - 1) % len(btn_cols)]
                with col:
                    if st.button(f"Analysis {idx}", key=f"an_btn_{a.get('id')}"):
                        st.session_state.selected_analysis_id = a.get('id')
            sel_id = st.session_state.get("selected_analysis_id") or items[0].get("id")
            sel = next((x for x in items if x.get("id") == sel_id), items[0])
            with st.expander(f"Analysis Details (ID: {sel.get('id')})", expanded=True):
                st.markdown(f"**When**: {sel.get('analysis_at_utc')}")
                st.markdown(f"**By**: {sel.get('analysis_by')} | **Role**: {sel.get('role')}")
                st.markdown(f"**Place**: {sel.get('place_of_analysis')}")
                st.markdown("**Description**")
                st.write(sel.get("description", ""))
                files = sel.get("files", [])
                if files:
                    st.markdown("**Files**")
                    for f in files:
                        fname = f.get("orig_filename")
                        st.write(f"- {fname} ({f.get('mime')}, {f.get('size_bytes')} bytes)")
                        if is_custodian:
                            if st.button("Download", key=f"an_dl_{sel.get('id')}_{f.get('id')}"):
                                okd, content, errd, dlname = st.session_state.api.download_analysis_file(int(sel.get('id')), int(f.get('id')))
                                if okd and content:
                                    st.download_button(
                                        label=f"Save {dlname or fname}",
                                        data=content,
                                        file_name=dlname or fname,
                                        mime=f.get("mime") or "application/octet-stream",
                                        key=f"an_save_{sel.get('id')}_{f.get('id')}"
                                    )
                                else:
                                    st.error(f"Download failed: {errd}")

    # Request transfer (current custodian only) with searchable user dropdown
    st.subheader("Request Transfer")
    users_ok, users, users_err = st.session_state.api.get_users()
    if not users_ok:
        st.error(f"Failed to load users: {users_err}")
        users = []
    # Build label->id mapping
    options = []
    label_to_id = {}
    for u in users or []:
        label = f"{u.get('name')} ({u.get('email')})"
        options.append(label)
        label_to_id[label] = int(u.get('id'))
    selected = st.selectbox("Recipient", options) if options else None
    reason = st.text_input("Reason", value="Routine transfer")
    if st.button("Request Transfer"):
        if not selected:
            st.error("Please select a recipient.")
        else:
            to_user_id = label_to_id.get(selected)
            if not to_user_id:
                st.error("Invalid recipient selection.")
            else:
                ok, res, err = st.session_state.api.request_transfer(int(eid), int(to_user_id), reason)
                if ok:
                    st.success("Transfer requested.")
                else:
                    st.error(f"Failed to request transfer: {err}")

    # Audit log timeline
    st.subheader("Audit Log")
    ok, audit, err = st.session_state.api.get_audit(int(eid))
    if ok and audit:
        entries = audit.get("audit_entries", []) if isinstance(audit, dict) else []
        if not entries:
            st.info("No audit entries.")
        else:
            # newest first
            try:
                entries = sorted(entries, key=lambda e: e.get("ts_utc") or "", reverse=True)
            except Exception:
                pass
            for idx, entry in enumerate(entries):
                ts = _format_ts(entry.get("ts_utc"))
                title_txt, chip = _action_badge(entry.get("action"))
                actor = entry.get("actor_name") or f"User #{entry.get('actor_user_id') or '—'}"
                details = entry.get("details") or {}
                ev_id_str = details.get("evidence_id_str") or entry.get("evidence_id_str")
                files = details.get("files") or []
                file_count = len(files) if isinstance(files, list) else 0

                # Card container
                key_id = str(entry.get("id") or idx)
                with st.container():
                    st.markdown(
                        f"""
                        <div class='coc-card audit-card'>
                          <div class='audit-head'>
                            <div class='audit-title'>{title_txt} <span class='coc-chip {chip}'>{entry.get('action')}</span></div>
                            <div class='audit-sub'>{ts}</div>
                          </div>
                          <div class='coc-muted' style='margin-top:.25rem;'>Actor: {actor} • Evidence: {ev_id_str or '—'} • Files: {file_count}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                    # Button inside the same visual card area
                    c1, c2 = st.columns([8, 2])
                    with c2:
                        show_key = f"show_audit_{key_id}"
                        if st.button("View metadata", key=f"btn_meta_{key_id}"):
                            st.session_state[show_key] = not st.session_state.get(show_key, False)
                    if st.session_state.get(show_key, False):
                        st.json(entry)
    else:
        st.error(f"Failed to load audit: {err}")


def user_list_page():
    if not require_login():
        return
    role = (st.session_state.user or {}).get("role", "").upper()
    if role != "ADMIN":
        st.warning("Admin only.")
        return
    st.title("User List")
    with st.spinner("Loading users..."):
        ok, users, err = st.session_state.api.get_users()
    if not ok:
        st.error(f"Failed to load users: {err}")
        return
    if not users:
        st.info("No users found.")
        return
    for u in users:
        with st.container():
            st.markdown(f"**{u.get('name')}** — {u.get('email')} | Role: {u.get('role')} | ID: {u.get('id')}")


def create_evidence_page():
    if not require_login():
        return

    role = (st.session_state.user or {}).get("role", "").upper()
    if role not in ("ANALYST", "COLLECTOR", "ADMIN"):
        st.warning("You do not have permissions to create evidence.")
        return

    st.title("Create Evidence")

    with st.form("evidence_form"):
        agency = st.text_input("Agency", "Demo PD")
        case_no = st.text_input("Case No", "2024-002")
        evidence_name = st.text_input("Evidence Name (optional)", "")
        offense = st.text_input("Offense", "Theft")
        item_no = st.text_input("Item No", "001")
        badge_no = st.text_input("Badge No", "1234")
        location = st.text_input("Location", "HQ")
        # Streamlit doesn't have datetime_input in this version; use date + time inputs
        default_dt = datetime.now(timezone.utc).replace(microsecond=0)
        collected_date = st.date_input("Collected Date", default_dt.date())
        collected_time = st.time_input("Collected Time", default_dt.time())
        dt = datetime.combine(collected_date, collected_time).replace(tzinfo=timezone.utc)
        description = st.text_area("Description", "Test item")

        uploaded_files = st.file_uploader("Upload files", type=None, accept_multiple_files=True)

        st.caption("Optional: Capture photo from camera")
        if CAM_AVAILABLE:
            cam_img = camera_input_live()
        else:
            cam_img = None
            st.info("Camera component not installed: streamlit-camera-input-live")

        # Removed: signature/sketch field per requirement

        submitted = st.form_submit_button("Create")

    if submitted:
        files_payload: List[Tuple[str, bytes, str]] = []

        # Regular uploads
        for uf in uploaded_files or []:
            files_payload.append((uf.name, uf.read(), uf.type or "application/octet-stream"))

        # Camera photo
        if cam_img is not None:
            files_payload.append(("camera.jpg", cam_img.getvalue(), "image/jpeg"))

        # Note: sketch/annotation upload removed

        if not files_payload:
            st.error("Please upload at least one file or use camera/canvas.")
            return

        collected_at_iso = dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        with st.spinner("Creating evidence..."):
            ok, res, err = st.session_state.api.create_evidence(
                agency=agency,
                case_no=case_no,
                offense=offense,
                item_no=item_no,
                badge_no=badge_no,
                location=location,
                collected_at_iso=collected_at_iso,
                description=description,
                evidence_name=evidence_name.strip() or None,
                files=files_payload,
            )
        if ok:
            st.success(f"Evidence created: ID {res.get('id')}")
            st.session_state.evidence_id = res.get("id")
            st.session_state.page = "evidence_detail"
            st.rerun()
        else:
            st.error(f"Failed to create evidence: {err}")


def admin_page():
    if not require_login():
        return

    role = (st.session_state.user or {}).get("role", "").upper()
    if role != "ADMIN":
        st.warning("Admin only.")
        return

    st.title("Admin Panel")

    st.subheader("Create User")
    with st.form("create_user_form"):
        name = st.text_input("Name")
        email = st.text_input("Email")
        role = st.selectbox("Role", ["ADMIN", "AUDITOR", "ANALYST", "COLLECTOR"])
        password = st.text_input("Password", type="password")
        sub = st.form_submit_button("Create User")
    if sub:
        ok, res, err = st.session_state.api.register_user(name, email, role, password)
        if ok:
            st.success(f"User created: {res.get('name')} ({res.get('role')})")
        else:
            st.error(f"Failed: {err}")

    st.markdown("---")
    st.subheader("All Evidence")
    ok, data, err = st.session_state.api.list_evidence(page=1, per_page=100)
    if ok and isinstance(data, dict):
        items = data.get("items", [])
        for ev in items:
            st.write(f"- {ev.get('evidence_id_str')} (ID: {ev.get('id')})")
    else:
        st.error(f"Failed to load evidence: {err}")


# ------------------------------
# Main routing
# ------------------------------

def main():
    st.set_page_config(page_title="Chain of Custody", layout="wide")
    init_state()

    if st.session_state.access_token:
        # ensure api client has token
        st.session_state.api.access_token = st.session_state.access_token

    page = st.session_state.page
    if page != "login" and not st.session_state.user and st.session_state.access_token:
        fetch_me()

    if page == "login":
        login_page()
    else:
        sidebar_nav()
        if st.session_state.page == "dashboard":
            dashboard_page()
        elif st.session_state.page == "evidence_detail":
            evidence_detail_page()
        elif st.session_state.page == "create":
            create_evidence_page()
        elif st.session_state.page == "admin":
            admin_page()
        elif st.session_state.page == "users":
            user_list_page()
        else:
            dashboard_page()


if __name__ == "__main__":
    main()
