# Smart Leave Pattern Analyzer

A Flask web application that analyzes leave patterns to detect anomalies.

## Setup

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000

## Demo Credentials

| Role     | Email                     | Password  |
|----------|---------------------------|-----------|
| Admin    | admin@smartleave.com      | admin123  |
| Employee | rahul@smartleave.com      | pass123   |
| Student  | priya@smartleave.com      | pass123   |

## Features

- Role-based access (Admin, Employee, Student)
- Leave application and approval workflow
- Pattern analysis: detects frequent short leaves, weekend extensions, holiday adjacency, high monthly frequency, continuous absenteeism
- Forgot Password / Password Reset functionality
- Charts for leave trends and type distribution
- User management (Admin)

## Project Structure

```
smart_leave/
├── app.py              # Flask app, models, routes, analysis logic
├── requirements.txt
├── static/
│   ├── css/style.css
│   └── js/main.js
└── templates/
    ├── base.html
    ├── login.html
    ├── dashboard_admin.html
    ├── dashboard_user.html
    ├── apply_leave.html
    ├── my_leaves.html
    ├── manage_leaves.html
    ├── analysis_admin.html
    ├── analysis_user.html
    ├── manage_users.html
    └── profile.html
```
