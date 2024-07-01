from django import forms


class VideoForm(forms.Form):
    video_url = forms.URLField(label="YouTube Video URL")
    start_time_minutes = forms.IntegerField(
        label="Start Time (Minutes)",
        min_value=0,
        initial=0,
        required=False,
    )
    start_time_seconds = forms.IntegerField(
        label="Start Time (Seconds)",
        min_value=0,
        initial=0,
        max_value=59,
        required=False,
    )
    end_time_minutes = forms.IntegerField(
        label="End Time (Minutes)",
        min_value=0,
        initial=0,
        required=False,
    )
    end_time_seconds = forms.IntegerField(
        label="End Time (Seconds)",
        min_value=0,
        initial=0,
        max_value=59,
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()
        start_time_minutes = cleaned_data.get("start_time_minutes")
        start_time_seconds = cleaned_data.get("start_time_seconds")
        end_time_minutes = cleaned_data.get("end_time_minutes")
        end_time_seconds = cleaned_data.get("end_time_seconds")

        if start_time_minutes is not None and end_time_minutes is not None:
            start_time = start_time_minutes * 60 + (start_time_seconds or 0)
            end_time = end_time_minutes * 60 + (end_time_seconds or 0)

            if start_time >= end_time:
                raise forms.ValidationError("มึงต้องการให้เล่นวิดีโอกลับหลังหรอ?")

        return cleaned_data
