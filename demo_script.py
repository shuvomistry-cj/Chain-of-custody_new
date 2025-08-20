#!/usr/bin/env python3
"""
Demo script to test Chain of Custody Evidence System functionality
"""
import requests
import json
import os
from pathlib import Path

BASE_URL = "http://localhost:8000"


class CoCDemo:
    def __init__(self):
        self.access_token = None
        self.admin_token = None
        self.users = {}
        self.evidence_id = None
        
    def login(self, email: str, password: str) -> str:
        """Login and return access token"""
        response = requests.post(f"{BASE_URL}/auth/login", json={
            "email": email,
            "password": password
        })
        
        if response.status_code == 200:
            data = response.json()
            return data["access_token"]
        else:
            print(f"Login failed: {response.text}")
            return None
    
    def register_user(self, name: str, email: str, role: str, password: str):
        """Register a new user (admin only)"""
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = requests.post(f"{BASE_URL}/auth/register", 
            headers=headers,
            json={
                "name": name,
                "email": email,
                "role": role,
                "password": password
            }
        )
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✓ Created user: {name} ({role})")
            return user_data
        else:
            print(f"✗ Failed to create user {name}: {response.text}")
            return None
    
    def create_test_file(self, filename: str, content: str):
        """Create a test file for upload"""
        with open(filename, "w") as f:
            f.write(content)
        return filename
    
    def create_evidence(self, token: str):
        """Create evidence with file upload"""
        # Create test files
        test_file1 = self.create_test_file("test_evidence.txt", "This is test evidence file 1")
        test_file2 = self.create_test_file("test_report.txt", "This is a test report file")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        files = [
            ("files", ("test_evidence.txt", open(test_file1, "rb"), "text/plain")),
            ("files", ("test_report.txt", open(test_file2, "rb"), "text/plain"))
        ]
        
        data = {
            "agency": "Demo Police Dept",
            "case_no": "2024-DEMO-001",
            "offense": "Cybercrime Investigation",
            "item_no": "ITEM-001",
            "badge_no": "BADGE-12345",
            "location": "123 Demo Street, Demo City",
            "collected_at": "2024-01-15T10:30:00Z",
            "description": "Demo evidence for testing chain of custody system"
        }
        
        try:
            response = requests.post(f"{BASE_URL}/evidence/", 
                headers=headers,
                files=files,
                data=data
            )
            
            # Close files
            for _, (_, file_obj, _) in files:
                file_obj.close()
            
            # Clean up test files
            os.remove(test_file1)
            os.remove(test_file2)
            
            if response.status_code == 200:
                evidence_data = response.json()
                self.evidence_id = evidence_data["id"]
                print(f"✓ Created evidence: {evidence_data['evidence_id_str']}")
                print(f"  Files: {len(evidence_data['files'])} uploaded")
                return evidence_data
            else:
                print(f"✗ Failed to create evidence: {response.text}")
                return None
                
        except Exception as e:
            print(f"✗ Error creating evidence: {e}")
            return None
    
    def request_transfer(self, token: str, evidence_id: int, to_user_id: int, reason: str):
        """Request evidence transfer"""
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{BASE_URL}/transfer/request",
            headers=headers,
            json={
                "evidence_id": evidence_id,
                "to_user_id": to_user_id,
                "reason": reason
            }
        )
        
        if response.status_code == 200:
            transfer_data = response.json()
            print(f"✓ Transfer requested: ID {transfer_data['id']}")
            return transfer_data
        else:
            print(f"✗ Failed to request transfer: {response.text}")
            return None
    
    def accept_transfer(self, token: str, transfer_id: int):
        """Accept pending transfer"""
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{BASE_URL}/transfer/accept/{transfer_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            transfer_data = response.json()
            print(f"✓ Transfer accepted: ID {transfer_data['id']}")
            return transfer_data
        else:
            print(f"✗ Failed to accept transfer: {response.text}")
            return None
    
    def get_audit_log(self, token: str, evidence_id: int):
        """Get audit log for evidence"""
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/audit/{evidence_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            audit_data = response.json()
            print(f"✓ Audit log retrieved: {len(audit_data['audit_entries'])} entries")
            return audit_data
        else:
            print(f"✗ Failed to get audit log: {response.text}")
            return None
    
    def download_file(self, token: str, evidence_id: int, file_id: int):
        """Download evidence file"""
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/evidence/{evidence_id}/download/{file_id}",
            headers=headers
        )
        
        if response.status_code == 200:
            filename = f"downloaded_file_{file_id}.txt"
            with open(filename, "wb") as f:
                f.write(response.content)
            print(f"✓ File downloaded: {filename}")
            return filename
        else:
            print(f"✗ Failed to download file: {response.text}")
            return None
    
    def run_demo(self):
        """Run complete demo scenario"""
        print("=== Chain of Custody Evidence System Demo ===\n")
        
        # Step 1: Login as admin
        print("1. Admin Login")
        admin_email = input("Admin email: ").strip()
        admin_password = input("Admin password: ").strip()
        
        self.admin_token = self.login(admin_email, admin_password)
        if not self.admin_token:
            print("Demo failed: Could not login as admin")
            return
        print("✓ Admin logged in successfully\n")
        
        # Step 2: Create demo users
        print("2. Creating Demo Users")
        collector = self.register_user("John Collector", "collector@demo.com", "COLLECTOR", "demo123")
        analyst = self.register_user("Jane Analyst", "analyst@demo.com", "ANALYST", "demo123")
        
        if not collector or not analyst:
            print("Demo failed: Could not create users")
            return
        
        # Login as collector
        collector_token = self.login("collector@demo.com", "demo123")
        analyst_token = self.login("analyst@demo.com", "demo123")
        
        if not collector_token or not analyst_token:
            print("Demo failed: Could not login as demo users")
            return
        print()
        
        # Step 3: Create evidence
        print("3. Creating Evidence with Files")
        evidence = self.create_evidence(collector_token)
        if not evidence:
            print("Demo failed: Could not create evidence")
            return
        print()
        
        # Step 4: Request transfer
        print("4. Requesting Transfer")
        transfer = self.request_transfer(
            collector_token, 
            evidence["id"], 
            analyst["id"], 
            "Transfer to analyst for detailed examination"
        )
        if not transfer:
            print("Demo failed: Could not request transfer")
            return
        print()
        
        # Step 5: Accept transfer
        print("5. Accepting Transfer")
        accepted = self.accept_transfer(analyst_token, transfer["id"])
        if not accepted:
            print("Demo failed: Could not accept transfer")
            return
        print()
        
        # Step 6: Download file as new custodian
        print("6. Downloading File (as new custodian)")
        if evidence["files"]:
            file_id = evidence["files"][0]["id"]
            downloaded = self.download_file(analyst_token, evidence["id"], file_id)
            if downloaded:
                # Clean up downloaded file
                os.remove(downloaded)
        print()
        
        # Step 7: View audit log
        print("7. Viewing Audit Log")
        audit_log = self.get_audit_log(analyst_token, evidence["id"])
        if audit_log:
            print("Audit entries:")
            for entry in audit_log["audit_entries"]:
                print(f"  - {entry['action']} by {entry['actor_name']} at {entry['ts_utc']}")
        print()
        
        # Step 8: Verify audit chain
        print("8. Verifying Audit Chain Integrity")
        headers = {"Authorization": f"Bearer {analyst_token}"}
        response = requests.get(f"{BASE_URL}/audit/{evidence['id']}/verify", headers=headers)
        
        if response.status_code == 200:
            verification = response.json()
            if verification["chain_valid"]:
                print("✓ Audit chain is valid and tamper-free")
            else:
                print("✗ Audit chain integrity compromised!")
        print()
        
        print("=== Demo Completed Successfully! ===")
        print(f"Evidence ID: {evidence['evidence_id_str']}")
        print(f"Total audit entries: {len(audit_log['audit_entries']) if audit_log else 0}")


if __name__ == "__main__":
    demo = CoCDemo()
    demo.run_demo()
