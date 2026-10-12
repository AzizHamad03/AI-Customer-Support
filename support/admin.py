from django.contrib import admin

from support.models import SupportTicket


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = [
        "reference",
        "status",
        "contact_email",
        "contact_phone",
        "created_at",
    ]
    list_filter = ["status"]
    search_fields = [
        "contact_email",
        "contact_phone",
        "description",
        "order_reference",
    ]
    readonly_fields = [
        "conversation",
        "request_id",
        "contact_email",
        "contact_phone",
        "description",
        "order_reference",
        "created_at",
        "updated_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False