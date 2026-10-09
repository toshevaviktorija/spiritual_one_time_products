import json
import re
from xml.etree import ElementTree
from django import forms
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from scripts.natal_chart.models import NatalChartData
from .models import Enquiry, Review, Feedback
from .validators import validate_public_email
from .terms import DELIVERY_CONSENT

class EnquiryForm(forms.ModelForm):
    email = forms.EmailField(validators=[validate_public_email], widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    class Meta:
        model = Enquiry
        fields = ["name", "email", "message"]
        labels = {"message": "Anything you would like us to know? (optional)"}
        widgets = {"message": forms.Textarea(attrs={"rows": 4}), "email": forms.EmailInput(attrs={"autocomplete": "email"}), "name": forms.TextInput(attrs={"autocomplete": "name"})}

class ReportForm(forms.Form):
    chart_json = forms.FileField(label="Natal chart JSON (.json or .txt)", required=False, widget=forms.ClearableFileInput(attrs={"accept": ".json,.txt"}))
    json_text = forms.CharField(label="Or paste the JSON text", required=False, widget=forms.Textarea(attrs={"rows": 6}))
    chart_svg = forms.FileField(label="Matching birth-chart SVG (.svg or .txt)", required=False, widget=forms.ClearableFileInput(attrs={"accept": ".svg,.txt"}))
    svg_text = forms.CharField(label="Or paste the SVG text", required=False, widget=forms.Textarea(attrs={"rows": 6}))

    def validate_chart_json(self):
        upload = self.cleaned_data["chart_json"]
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose a JSON file smaller than 5 MB.")
        try:
            payload = json.loads(upload.read())
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            self.chart_data = NatalChartData.from_mapping(payload)
        except (ValueError, TypeError, AttributeError, UnicodeDecodeError, RecursionError):
            raise forms.ValidationError("Upload valid natal-chart JSON containing subject_data and chart_data.")
        upload.seek(0)
        return upload

    def validate_chart_svg(self):
        upload = self.cleaned_data["chart_svg"]
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an SVG file smaller than 5 MB.")
        raw = upload.read()
        try:
            text = raw.decode("utf-8")
            if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
                raise ValueError()
            root = ElementTree.fromstring(text)
            if root.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError()
            for node in root.iter():
                if node.tag.rsplit("}", 1)[-1] in {"script", "foreignObject", "image"}:
                    raise ValueError()
                for key, value in node.attrib.items():
                    if key.rsplit("}", 1)[-1] == "href" and not value.startswith("#"):
                        raise ValueError()
            if re.search(r"@import", text, re.I):
                raise ValueError()
            for target in re.findall(r"url\(([^)]*)\)", text, re.I):
                if not target.strip().strip("\"'").startswith('#'):
                    raise ValueError()
        except (ValueError, ElementTree.ParseError):
            raise forms.ValidationError("Choose a self-contained chart SVG without images, scripts or external references.")
        upload.seek(0)
        return upload

    def clean(self):
        cleaned = super().clean()
        for file_field, text_field, validator in [('chart_json', 'json_text', self.validate_chart_json), ('chart_svg', 'svg_text', self.validate_chart_svg)]:
            upload, text = cleaned.get(file_field), cleaned.get(text_field)
            if bool(upload) == bool(text):
                self.add_error(file_field, 'Provide either a file or pasted text for this chart, but not both.')
                continue
            if text:
                cleaned[file_field] = SimpleUploadedFile(file_field + '.txt', text.encode('utf-8'))
            try:
                cleaned[file_field] = validator()
            except forms.ValidationError as error:
                self.add_error(file_field, error)
        return cleaned

class BirthDetailsForm(forms.Form):
    early_delivery_consent = forms.BooleanField(label=DELIVERY_CONSENT, required=True, error_messages={"required": "Please confirm the digital delivery and cancellation terms to continue to Checkout."})
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    email = forms.EmailField(validators=[validate_public_email], label='Email address', widget=forms.EmailInput(attrs={'autocomplete': 'email'}))
    birth_date = forms.DateField(label='Date of birth', input_formats=['%Y-%m-%d'], widget=forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date', 'autocomplete': 'bday'}))
    birth_time = forms.TimeField(label='Time of birth', required=False, input_formats=['%H:%M', '%H:%M:%S'], widget=forms.TimeInput(format='%H:%M', attrs={'type': 'time', 'step': '60'}))
    unknown_birth_time = forms.BooleanField(label="I don’t know my birth time", required=False)
    hour = forms.IntegerField(widget=forms.HiddenInput, required=False, min_value=0, max_value=23, help_text='Optional. Defaults to 12 (noon).')
    minute = forms.IntegerField(widget=forms.HiddenInput, required=False, min_value=0, max_value=59, help_text='Optional. Defaults to 0.')
    second = forms.IntegerField(widget=forms.HiddenInput, required=False, min_value=0, max_value=59, help_text='Optional. Defaults to 0.')
    city = forms.CharField(max_length=200, widget=forms.HiddenInput, error_messages={'required': 'Please select your birth town from the location search.'})
    countryCode = forms.RegexField(widget=forms.HiddenInput, regex=r'^[A-Za-z]{2}$', label='Country code', max_length=2, help_text='Two-letter country code, for example GB.', error_messages={'invalid': 'Please choose a valid location from the search.', 'required': 'Please select your birth town from the location search.'})

    def __init__(self, data=None, *args, require_delivery_consent=False, **kwargs):
        # Keep compatibility with existing callers that submit separate date parts.
        if data is not None and 'birth_date' not in data and all(key in data for key in ('year', 'month', 'day')):
            data = data.copy()
            try:
                data['birth_date'] = f"{int(data['year']):04d}-{int(data['month']):02d}-{int(data['day']):02d}"
            except (TypeError, ValueError):
                data['birth_date'] = ''
        super().__init__(data, *args, **kwargs)
        consent = self.fields.pop('early_delivery_consent')
        if require_delivery_consent:
            self.fields['early_delivery_consent'] = consent
        self.fields['birth_date'].widget.attrs['max'] = timezone.localdate().isoformat()

    def clean_countryCode(self):
        return self.cleaned_data['countryCode'].upper()

    def clean_birth_date(self):
        birthday = self.cleaned_data['birth_date']
        if birthday > timezone.localdate():
            raise forms.ValidationError('Birth date cannot be in the future.')
        return birthday

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('unknown_birth_time'):
            cleaned.update(hour=12, minute=0, second=0)
        elif cleaned.get('birth_time') is not None:
            clock = cleaned['birth_time']
            cleaned.update(hour=clock.hour, minute=clock.minute, second=clock.second)
        return cleaned

    def payload(self):
        data = self.cleaned_data
        birthday = data['birth_date']
        return {'name': data['name'], 'birthData': {'year': birthday.year, 'month': birthday.month, 'day': birthday.day, 'hour': 12 if data['hour'] is None else data['hour'], 'minute': 0 if data['minute'] is None else data['minute'], 'second': 0 if data['second'] is None else data['second'], 'city': data['city'], 'countryCode': data['countryCode']}}


class ReviewForm(forms.ModelForm):
    rating = forms.TypedChoiceField(label='Your rating', choices=[(n, f"{n} ★") for n in range(1, 6)], coerce=int, initial=5, widget=forms.RadioSelect(attrs={'class': 'star-options'}))

    class Meta:
        model = Review
        fields = ['rating', 'text']
        labels = {'text': 'Your review'}
        widgets = {'text': forms.Textarea(attrs={'rows': 5, 'maxlength': 2000})}

class FeedbackForm(forms.ModelForm):
    class Meta:
        model = Feedback
        fields = ['text']
        labels = {'text': 'Your private feedback'}
        widgets = {'text': forms.Textarea(attrs={'rows': 5, 'maxlength': 2000})}


class ChartEmailForm(forms.Form):
    report = forms.ModelChoiceField(queryset=None, label='PDF attachment')
    subject = forms.CharField(max_length=200, initial='Your Venastella natal chart is ready ✧')
    message = forms.CharField(max_length=10000, widget=forms.Textarea(attrs={'rows': 8}))

    def __init__(self, *args, birth_request, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Report
        self.fields['report'].queryset = Report.objects.filter(birth_request=birth_request).exclude(chartemail__submitted_at__isnull=False)
        self.fields['report'].initial = self.fields['report'].queryset.first()
        self.fields['message'].initial = f"Hello {birth_request.payload.get('name', '')},\n\nYour personal celestial portrait is ready. You’ll find your natal chart attached as a PDF, made for slow reading and moments of discovery.\n\nI hope it brings you insight and inspiration. If you have any questions, simply reply to this email."


class InspectEmailForm(forms.Form):
    inspected = forms.BooleanField(label='I downloaded and inspected this PDF and checked the recipient and message.')
