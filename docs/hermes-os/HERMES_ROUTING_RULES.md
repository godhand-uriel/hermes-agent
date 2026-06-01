# Hermes Routing Rules

## Purpose

Route every task to the correct Hermes profile so work does not drift or duplicate.

## Primary Rule

If a task affects multiple domains, Command Center owns triage and delegates child tasks.

## Routing Matrix

| Task Type                   | Owner              |
| --------------------------- | ------------------ |
| Strategic planning          | command_center     |
| Executive review            | command_center     |
| Board health                | command_center     |
| Escalations                 | command_center     |
| Business idea               | venture_portfolio  |
| Market research             | venture_portfolio  |
| MVP planning                | venture_portfolio  |
| Venture scoring             | venture_portfolio  |
| Software development        | engineering_lab    |
| Bug fix                     | engineering_lab    |
| Testing                     | engineering_lab    |
| Infrastructure              | engineering_lab    |
| Hermes platform improvement | engineering_lab    |
| Certifications              | career_development |
| WGU roadmap                 | career_development |
| Job applications            | career_development |
| Interview prep              | career_development |
| Resume optimization         | career_development |
| YouTube content             | engineering_brand  |
| Portfolio project showcase  | engineering_brand  |
| Technical writing           | engineering_brand  |
| Consulting proposal         | consulting_office  |
| SOW creation                | consulting_office  |
| Pricing/retainers           | consulting_office  |
| Client delivery             | consulting_office  |
| Artist collection           | artist_management  |
| Gallery outreach            | artist_management  |
| Collector relations         | artist_management  |
| Art pricing                 | artist_management  |

## Escalation Rules

* Blocked more than 24 hours → command_center.
* Revenue opportunity unclear → venture_portfolio.
* Technical risk unclear → engineering_lab.
* Career impact unclear → career_development.
* Client/revenue delivery unclear → consulting_office.

## Forbidden Routing

* Do not send coding tasks to non-technical profiles.
* Do not let venture_portfolio build before validation.
* Do not let engineering_lab decide business priority alone.
* Do not let command_center implement code.
