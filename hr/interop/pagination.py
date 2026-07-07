"""HR-Open flavoured pagination.

Wraps a page of already-mapped HR-Open records in a self-describing envelope
with ``links`` (self/next/prev) and ``meta`` (counts), aligned with the
REST/JSON conventions HR Open Standards moved to for its API profile.
"""

from __future__ import annotations

from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from . import HR_OPEN_PROFILE_VERSION, HR_OPEN_STANDARD


class HROpenPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 200

    def get_paginated_response(self, data):
        paginator = self.page.paginator
        return Response(
            {
                "standard": HR_OPEN_STANDARD,
                "version": HR_OPEN_PROFILE_VERSION,
                "data": data,
                "links": {
                    "self": self.request.build_absolute_uri(),
                    "next": self.get_next_link(),
                    "prev": self.get_previous_link(),
                },
                "meta": {
                    "totalCount": paginator.count,
                    "pageCount": paginator.num_pages,
                    "page": self.page.number,
                    "pageSize": self.get_page_size(self.request),
                },
            }
        )
