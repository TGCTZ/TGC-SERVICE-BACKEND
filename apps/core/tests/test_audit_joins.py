"""The audit labels must not cost a query per row."""

import pytest

from apps.core.current_user import reset_current_user, set_current_user
from apps.gems.tests.factories import StoneTypeFactory
from apps.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _stamped_rows(count):
    """Create rows inside a request context, so the actor columns are set."""
    actor = UserFactory()
    token = set_current_user(actor)
    try:
        for index in range(count):
            StoneTypeFactory(name=f"Stamped {index}")
    finally:
        reset_current_user(token)


@pytest.mark.parametrize("rows", [1, 10])
def test_list_query_count_does_not_grow_with_rows(
    rows, admin_user, auth_client, django_assert_max_num_queries
):
    """AuditFieldsMixin renders created_by/updated_by as display labels.

    Dereferencing those two foreign keys is one extra query per row unless the
    base ViewSet joins them. The rows here are created *inside* a current-user
    context on purpose: a plain factory leaves the actor columns null, the label
    methods short-circuit, and the N+1 hides completely - which is exactly how
    it survived until now.
    """
    _stamped_rows(rows)

    client = auth_client(admin_user)
    with django_assert_max_num_queries(7):
        response = client.get(f"/api/v1/stone-types/?page_size={rows}")

    assert response.status_code == 200
    assert response.data["results"][0]["created_by_label"] is not None
