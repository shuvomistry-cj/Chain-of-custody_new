import io
import json
from datetime import datetime, timezone
from typing import List, Tuple

import streamlit as st
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


def dashboard_page():
    if not require_login():
        return

    st.title("Dashboard")

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
        for ev in items:
            col1, col2, col3 = st.columns([4, 2, 2])
            with col1:
                st.write(f"{ev.get('evidence_id_str')} (ID: {ev.get('id')})")
                st.caption(ev.get("description", ""))
            with col2:
                if st.button("View", key=f"view_{ev.get('id')}"):
                    st.session_state.evidence_id = ev.get("id")
                    st.session_state.page = "evidence_detail"
                    st.rerun()
            with col3:
                st.write("")

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

    ok, ev, err = st.session_state.api.get_evidence(eid)
    if not ok or not ev:
        st.error(f"Failed to load evidence: {err}")
        return

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
            for entry in entries:
                with st.expander(f"{entry.get('ts_utc')} - {entry.get('action')}"):
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
