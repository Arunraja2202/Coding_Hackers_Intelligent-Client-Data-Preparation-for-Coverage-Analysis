# API endpoints

- `POST /api/login` - create session
- `POST /api/logout` - clear session
- `GET /api/health` - service and CSI configuration status
- `POST /api/upload` - upload one file and queue transformation
- `GET /api/jobs` - job history
- `GET /api/jobs/{id}` - job status/progress
- `GET /api/jobs/{id}/download/output` - transformed dataset
- `GET /api/jobs/{id}/download/errors` - data-quality issue log
- `GET /api/jobs/{id}/download/report` - reconciliation/method report
- `GET /api/templates` - list client templates
- `POST /api/templates` - create/update template
