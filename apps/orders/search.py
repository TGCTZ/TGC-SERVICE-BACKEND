"""Search whitelists for orders and stones, shared across apps.

The worklist endpoints live in ``billing``, ``identification`` and
``certificates`` but return Orders and Stones, so each one would otherwise
hand-roll the same field list against a model it does not own - and they would
drift the moment a column was added to a queue's columns. These are the one
copy, and ``apps.orders.views`` reads them too.
"""

#: Order fields a queue search covers - what an order's row actually shows.
ORDER_SEARCH_FIELDS = (
    "reference_number",
    "customer__first_name",
    "customer__last_name",
    "customer__phone",
)

#: Stone fields a queue search covers.
#:
#: Wider than ``StoneViewSet.search_fields``: a stone row in a queue also prints
#: the customer's name and phone, and a gemmologist holding a parcel searches by
#: the person who brought it as readily as by the stone's label.
STONE_SEARCH_FIELDS = (
    "label",
    "order__reference_number",
    "stone_type__name",
    "order__customer__first_name",
    "order__customer__last_name",
    "order__customer__phone",
)
