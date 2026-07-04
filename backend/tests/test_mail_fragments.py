"""Tests for mail context fragments."""

import asyncio
import os

from app.context_runtime import FragmentRegistry, RuntimeContext


class TestMailFragments:
    def test_recent_emails_fragment_includes_identity(self):
        from app.fragments.mail import RecentEmailsFragment

        f = RecentEmailsFragment()
        assert f.id == "mail.recent_emails"

        result = asyncio.run(f.collect(RuntimeContext()))
        assert "mail assistant" in result.content.lower()

    def test_recent_emails_fragment_exists(self):
        from app.fragments.mail import RecentEmailsFragment

        f = RecentEmailsFragment()
        assert f.id == "mail.recent_emails"

    def test_email_search_fragment_exists(self):
        from app.fragments.mail import EmailSearchFragment

        assert EmailSearchFragment().id == "mail.email_search"

    def test_fragment_has_no_kernel_reference(self):
        from app.fragments.mail import RecentEmailsFragment

        f = RecentEmailsFragment()
        assert not hasattr(f, "_kernel")
        assert not hasattr(f, "emit")
        assert not hasattr(f, "emit_event")


class TestFragmentRegistry:
    def test_fragment_registry_register_and_get(self):
        from app.fragments.mail import RecentEmailsFragment

        registry = FragmentRegistry()
        f = RecentEmailsFragment()
        registry.register(f)

        assert registry.get("mail.recent_emails") is not None
        assert registry.get("mail.recent_emails").id == "mail.recent_emails"

    def test_fragment_registry_get_nonexistent(self):
        registry = FragmentRegistry()
        assert registry.get("nonexistent") is None

    def test_fragment_registry_list_ids(self):
        from app.fragments.mail import RecentEmailsFragment, EmailSearchFragment

        registry = FragmentRegistry()
        registry.register(RecentEmailsFragment())
        registry.register(EmailSearchFragment())

        ids = registry.list_ids()
        assert "mail.recent_emails" in ids
        assert "mail.email_search" in ids

    def test_register_all_fragments_includes_mail(self):
        from app.fragments.register import register_all_fragments

        registry = FragmentRegistry()
        ids = register_all_fragments(registry)
        assert "mail.recent_emails" in ids
        assert "mail.email_search" in ids
        assert "mail.email_thread" not in ids
        assert len(ids) == 10


class TestRuntimeGovernanceGuarantees:
    def test_fragment_does_not_hold_kernel_reference(self):
        from app.fragments.mail import RecentEmailsFragment, EmailSearchFragment

        for f in [RecentEmailsFragment(), EmailSearchFragment()]:
            assert not hasattr(f, "_kernel")
            assert not hasattr(f, "emit_event")
            assert not hasattr(f, "invoke_capability")

    def test_registry_is_pure_data_management(self):
        registry = FragmentRegistry()
        assert hasattr(registry, "register")
        assert hasattr(registry, "get")
        assert hasattr(registry, "list_all")
        assert not hasattr(registry, "resolve_tool_scope")
        assert not hasattr(registry, "visible_for")


class TestDeletedConcepts:
    def test_no_domain_package(self):
        domains_dir = os.path.join(
            os.path.dirname(__file__), "..", "app", "domains"
        )
        assert not os.path.isdir(domains_dir)

    def test_mail_fragment_package_exists(self):
        mail_dir = os.path.join(
            os.path.dirname(__file__), "..", "app", "fragments", "mail"
        )
        assert os.path.isdir(mail_dir)

    def test_no_runtime_identity_fragment(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "app", "fragments", "universal", "runtime_identity.py"
        )
        assert not os.path.isfile(path)


class TestContextReduction:
    def test_mail_fragment_count(self):
        from app.fragments.mail import (
            EmailSearchFragment,
            RecentEmailsFragment,
        )

        fragments = [
            RecentEmailsFragment(),
            EmailSearchFragment(),
        ]
        assert len(fragments) == 2

    def test_identity_included_in_recent_emails_fragment(self):
        from app.fragments.mail import RecentEmailsFragment

        f = RecentEmailsFragment()
        result = asyncio.run(f.collect(RuntimeContext()))
        assert len(result.content) < 2000
