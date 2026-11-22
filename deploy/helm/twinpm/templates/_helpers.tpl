{{- define "twinpm.labels" -}}
app.kubernetes.io/part-of: twinpm
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
{{- define "twinpm.env" -}}
{{- range $k, $v := .Values.env }}
- name: {{ $k }}
  value: {{ $v | quote }}
{{- end }}
- name: MODELS_DIR
  value: /app/models
{{- end }}
