from django import forms

from support.models import KnowledgeDocument, SupportTicket
from django import forms
from support.models import KnowledgeDocument

class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = KnowledgeDocument
        fields = ["title", "category", "file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={"accept": ".pdf,.txt"}
            ),
        }
        help_texts = {
            "file": "Upload a text-based PDF or UTF-8 TXT file, up to 10 MB.",
        }

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("Enter a document title.")
        return title

class KnowledgeSearchForm(forms.Form):
    question = forms.CharField(
        label="Test question",
        max_length=500,
        widget=forms.TextInput(
            attrs={
                "placeholder": "For example: How much does shipping cost?",
            }
        ),
    )

class SupportTicketForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = [
            "contact_email",
            "contact_phone",
            "description",
            "order_reference",
        ]
        labels = {
            "contact_email": "Email address",
            "contact_phone": "Phone number",
            "description": "What do you need help with?",
            "order_reference": "Order reference",
        }
        help_texts = {
            "contact_email": "Provide an email address or a phone number.",
            "contact_phone": "Optional if you provide an email address.",
            "description": "Describe the issue in 10–2000 characters.",
            "order_reference": "Optional. Include it if available.",
        }
        widgets = {
            "description": forms.Textarea(
                attrs={"rows": 5, "maxlength": 2000}
            ),
        }

class TicketFilterForm(forms.Form):
    q = forms.CharField(
        label="Search",
        required=False,
        max_length=100,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ticket reference, contact, order, or issue",
            }
        ),
    )
    status = forms.ChoiceField(
        required=False,
        choices=[
            ("", "All statuses"),
            *SupportTicket.Status.choices,
        ],
    )


class TicketStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=SupportTicket.Status.choices,
    )

class DocumentReplacementForm(forms.ModelForm):
    class Meta:
        model = KnowledgeDocument
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={"accept": ".pdf,.txt"}
            ),
        }
        help_texts = {
            "file": "Upload a PDF or UTF-8 TXT file, up to 10 MB.",
        }