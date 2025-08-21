import requests
from typing import Any, Dict, List, Optional, Tuple


class APIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        self.access_token: Optional[str] = None

    # ---------- internal helpers ----------
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        if extra:
            headers.update(extra)
        return headers

    def _handle(self, resp: requests.Response) -> Tuple[bool, Any, Optional[str]]:
        try:
            if resp.headers.get("content-type", "").startswith("application/json"):
                data = resp.json()
            else:
                data = resp.content
        except Exception:
            data = resp.text
        if resp.ok:
            return True, data, None
        else:
            # FastAPI returns {"detail": ...}
            if isinstance(data, dict) and "detail" in data:
                detail = data["detail"]
                if isinstance(detail, list):
                    msg = "; ".join([str(d.get("msg", d)) for d in detail])
                else:
                    msg = str(detail)
            else:
                msg = str(data)
            return False, None, msg

    # ---------- auth ----------
    def login(self, email: str, password: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/login"
        resp = requests.post(url, json={"email": email, "password": password})
        ok, data, err = self._handle(resp)
        if ok and isinstance(data, dict):
            self.access_token = data.get("access_token")
        return ok, data if ok else None, err

    def me(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/me"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def password_reset_request(self, email: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/password-reset/request"
        resp = requests.post(url, json={"email": email}, headers=self._headers({"Content-Type": "application/json"}))
        return self._handle(resp)

    def password_reset_confirm(self, token: str, new_password: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/password-reset/confirm"
        resp = requests.post(url, json={"token": token, "new_password": new_password}, headers=self._headers({"Content-Type": "application/json"}))
        return self._handle(resp)

    # ---------- evidence ----------
    def list_evidence(self, page: int = 1, per_page: int = 20) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/evidence/"  # trailing slash avoids redirect/auth loss
        params = {"page": page, "per_page": per_page}
        resp = requests.get(url, params=params, headers=self._headers())
        return self._handle(resp)

    def get_evidence(self, evidence_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/evidence/{evidence_id}"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def create_evidence(
        self,
        agency: str,
        case_no: str,
        offense: str,
        item_no: str,
        badge_no: str,
        location: str,
        collected_at_iso: str,
        description: str,
        evidence_name: Optional[str],
        files: List[Tuple[str, bytes, str]],  # (filename, content, mime)
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/evidence/"  # trailing slash
        # Build multipart/form-data
        data = {
            "agency": agency,
            "case_no": case_no,
            "offense": offense,
            "item_no": item_no,
            "badge_no": badge_no,
            "location": location,
            "collected_at": collected_at_iso,
            "description": description,
        }
        if evidence_name:
            data["evidence_name"] = evidence_name
        # Multiple files under the same key 'files'
        files_payload = [("files", (fname, content, mime)) for (fname, content, mime) in files]
        resp = requests.post(url, data=data, files=files_payload, headers=self._headers())
        return self._handle(resp)

    def download_file(self, evidence_id: int, file_id: int) -> Tuple[bool, Optional[bytes], Optional[str], Optional[str]]:
        url = f"{self.base_url}/evidence/{evidence_id}/download/{file_id}"
        resp = requests.get(url, headers=self._headers(), stream=True)
        if resp.ok:
            filename = None
            cd = resp.headers.get("Content-Disposition")
            if cd and "filename=" in cd:
                filename = cd.split("filename=")[-1].strip().strip('"')
            return True, resp.content, None, filename
        else:
            ok, _, err = self._handle(resp)
            return False, None, err, None

    # ---------- transfers ----------
    def list_pending_transfers(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        url = f"{self.base_url}/transfer/pending"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def request_transfer(self, evidence_id: int, to_user_id: int, reason: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/transfer/request"
        payload = {"evidence_id": evidence_id, "to_user_id": to_user_id, "reason": reason}
        resp = requests.post(url, json=payload, headers=self._headers({"Content-Type": "application/json"}))
        return self._handle(resp)

    def list_outgoing_pending_transfers(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        url = f"{self.base_url}/transfer/pending-outgoing"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def cancel_transfer(self, transfer_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/transfer/cancel/{transfer_id}"
        resp = requests.post(url, headers=self._headers())
        return self._handle(resp)

    def accept_transfer(self, transfer_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/transfer/accept/{transfer_id}"
        resp = requests.post(url, headers=self._headers())
        return self._handle(resp)

    def reject_transfer(self, transfer_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/transfer/reject/{transfer_id}"
        resp = requests.post(url, headers=self._headers())
        return self._handle(resp)

    # ---------- audit ----------
    def get_audit(self, evidence_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/audit/{evidence_id}"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def verify_audit(self, evidence_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/audit/{evidence_id}/verify"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    # ---------- admin ----------
    def register_user(
        self,
        name: str,
        email: str,
        role: str,
        password: str,
        organization: Optional[str] = None,
        department: Optional[str] = None,
        employee_id: Optional[str] = None,
        national_id: Optional[str] = None,
        authorised_by: Optional[str] = None,
        photo_url: Optional[str] = None,
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/register"
        payload: Dict[str, Any] = {
            "name": name,
            "email": email,
            "role": role,
            "password": password,
        }
        # Include optional fields only if provided
        if organization is not None:
            payload["organization"] = organization
        if department is not None:
            payload["department"] = department
        if employee_id is not None:
            payload["employee_id"] = employee_id
        if national_id is not None:
            payload["national_id"] = national_id
        if authorised_by is not None:
            payload["authorised_by"] = authorised_by
        if photo_url is not None:
            payload["photo_url"] = photo_url
        resp = requests.post(url, json=payload, headers=self._headers({"Content-Type": "application/json"}))
        return self._handle(resp)

    def get_users(self) -> Tuple[bool, Optional[List[Dict[str, Any]]], Optional[str]]:
        url = f"{self.base_url}/auth/users"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def update_user(self, user_id: int, role: str) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """ADMIN: update limited user fields. Currently supports role changes only."""
        url = f"{self.base_url}/auth/users/{user_id}"
        payload = {"role": role}
        resp = requests.patch(url, json=payload, headers=self._headers({"Content-Type": "application/json"}))
        return self._handle(resp)

    # ---------- profiles ----------
    def get_user_profile(self, user_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/users/{user_id}/profile"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def update_user_profile(self, user_id: int, profile: Dict[str, Any]) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/users/{user_id}/profile"
        resp = requests.patch(url, json=profile, headers=self._headers({"Content-Type": "application/json"}))
        return self._handle(resp)

    def get_my_profile(self) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/auth/me/profile"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    # ---------- analysis ----------
    def list_analyses(self, evidence_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/analysis/by-evidence/{evidence_id}"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def create_analysis(
        self,
        evidence_id: int,
        analysis_at_iso: str,
        analysis_by: str,
        role: str,
        place_of_analysis: str,
        description: str,
        files: List[Tuple[str, bytes, str]],
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/analysis/"
        data = {
            "evidence_id": str(evidence_id),
            "analysis_at_iso": analysis_at_iso,
            "analysis_by": analysis_by,
            "role": role,
            "place_of_analysis": place_of_analysis,
            "description": description,
        }
        files_payload = [("files", (fname, content, mime)) for (fname, content, mime) in files]
        resp = requests.post(url, data=data, files=files_payload, headers=self._headers())
        return self._handle(resp)

    def get_analysis(self, analysis_id: int) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        url = f"{self.base_url}/analysis/{analysis_id}"
        resp = requests.get(url, headers=self._headers())
        return self._handle(resp)

    def download_analysis_file(self, analysis_id: int, file_id: int) -> Tuple[bool, Optional[bytes], Optional[str], Optional[str]]:
        url = f"{self.base_url}/analysis/{analysis_id}/download/{file_id}"
        resp = requests.get(url, headers=self._headers(), stream=True)
        if resp.ok:
            filename = None
            cd = resp.headers.get("Content-Disposition")
            if cd and "filename=" in cd:
                filename = cd.split("filename=")[-1].strip().strip('"')
            return True, resp.content, None, filename
        else:
            ok, _, err = self._handle(resp)
            return False, None, err, None
