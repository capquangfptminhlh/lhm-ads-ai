"""Offline regression for guarded Cloudflare D1 and Access bootstrap.

No real network requests, no secrets, no Cloudflare mutations.
"""
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
import deploy_commerce
import bootstrap_access

DB_UUID="12345678-1234-1234-1234-123456789abc"
AUD="a"*64
OWNER="owner@example.invalid"


class CloudflareBootstrapTests(unittest.TestCase):
    def test_existing_d1_is_reused(self):
        mock_result=types.SimpleNamespace(stdout='[{"name":"lhm-ads-commerce","uuid":"'+DB_UUID+'"}]')
        with patch.object(deploy_commerce.subprocess,"run",return_value=mock_result) as run:
            self.assertEqual(deploy_commerce.find_database_id(),DB_UUID)
            run.assert_called_once()

    def test_missing_d1_never_created_without_opt_in(self):
        mock_result=types.SimpleNamespace(stdout='[]')
        with patch.object(deploy_commerce.subprocess,"run",return_value=mock_result):
            with patch.object(deploy_commerce,"create_database") as create:
                with self.assertRaises(deploy_commerce.RuntimeError):
                    deploy_commerce.find_database_id()
                create.assert_not_called()
                create.return_value=DB_UUID
                self.assertEqual(deploy_commerce.find_database_id(create_missing=True),DB_UUID)

    def test_mismatched_d1_name_does_not_deploy(self):
        mock_result=types.SimpleNamespace(stdout='[{"name":"unrelated","uuid":"'+DB_UUID+'"}]')
        with patch.object(deploy_commerce.subprocess,"run",return_value=mock_result):
            with self.assertRaises(deploy_commerce.RuntimeError):
                deploy_commerce.find_database_id()

    def test_d1_config_only_uses_verified_binding(self):
        rendered=deploy_commerce.make_config(DB_UUID)
        self.assertIn('binding = "COMMERCE_DB"',rendered)
        self.assertIn(DB_UUID,rendered)
        self.assertIn('migrations_dir = "migrations"',rendered)
        self.assertIn('keep_vars = true',rendered)

    def fake_api(self,existing=None):
        def handler(method,path,body=None):
            if path=="/access/organizations" and method=="GET":
                return {"auth_domain":"example.cloudflareaccess.com"}
            if path=="/access/apps" and method=="GET":
                return [] if existing is None else [existing]
            if path=="/access/apps" and method=="POST":
                assert body is not None
                self.assertEqual(body["type"],"self_hosted")
                self.assertEqual(
                    {d["uri"] for d in body["destinations"]},
                    bootstrap_access.TARGETS)
                self.assertEqual(body["policies"][0]["include"],
                                 [{"email":{"email":OWNER}}])
                return {**body,"aud":AUD}
            raise AssertionError((method,path))
        return handler

    def test_access_app_requires_explicit_create(self):
        with patch.dict(os.environ,{"LHM_ADMIN_EMAIL":OWNER}):
            with patch.object(bootstrap_access,"api",side_effect=self.fake_api()):
                with self.assertRaises(bootstrap_access.BootstrapError):
                    bootstrap_access.bootstrap(create=False)

    def test_access_app_created_only_for_three_target_paths(self):
        with patch.dict(os.environ,{"LHM_ADMIN_EMAIL":OWNER}):
            with patch.object(bootstrap_access,"api",side_effect=self.fake_api()) as api:
                result=bootstrap_access.bootstrap(create=True)
                self.assertEqual(result["aud"],AUD)
                self.assertEqual(result["team_domain"],"example.cloudflareaccess.com")
                self.assertEqual(result["email"],OWNER)
                self.assertEqual(len(api.mock_calls),3)

    def test_existing_app_does_not_get_replaced(self):
        existing={
            "name":bootstrap_access.NAME,"type":"self_hosted",
            "aud":AUD,"destinations":[{"uri":v,"type":"public"} for v in bootstrap_access.TARGETS]
        }
        with patch.dict(os.environ,{"LHM_ADMIN_EMAIL":OWNER}):
            with patch.object(bootstrap_access,"api",side_effect=self.fake_api(existing)):
                result=bootstrap_access.bootstrap(create=True)
                self.assertEqual(result["aud"],AUD)

    def test_access_conflict_is_not_overwritten(self):
        existing={"name":bootstrap_access.NAME,"aud":AUD,"destinations":[
            {"uri":"ads.lhmcrm.com","type":"public"}]}
        with patch.dict(os.environ,{"LHM_ADMIN_EMAIL":OWNER}):
            with patch.object(bootstrap_access,"api",side_effect=self.fake_api(existing)):
                with self.assertRaises(bootstrap_access.BootstrapError):
                    bootstrap_access.bootstrap(create=True)

    def test_missing_owner_email_is_rejected(self):
        with patch.dict(os.environ,{"LHM_ADMIN_EMAIL":""}):
            with patch.object(bootstrap_access,"api") as api:
                with self.assertRaises(bootstrap_access.BootstrapError):
                    bootstrap_access.bootstrap(create=True)
                api.assert_not_called()


if __name__=="__main__":
    unittest.main()
