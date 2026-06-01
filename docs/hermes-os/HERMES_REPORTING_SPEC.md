# Hermes Reporting Spec

## Purpose

Define default reporting cadence for Hermes across Yuu's operating system, career, engineering work, and venture portfolio.

## Timezone

America/New_York.

## Default Delivery Channel

Telegram home channel.

## Daily Morning Brief

Time: 9:00 AM.

Includes:

* Top 3 priorities
* Blocked tasks
* Review-required tasks
* Today's deadlines
* Recommended focus order

Owner:
command_center

## Daily Evening Report

Time: 6:00 PM.

Includes:

* Completed tasks
* Newly blocked tasks
* Tasks needing review
* Progress by profile
* Tomorrow's recommended priorities

Owner:
command_center

## Blocker Watch

Cadence: every 4 hours.

Includes:

* Tasks blocked more than 24 hours
* Ready tasks with no worker
* Running tasks with stale heartbeat
* Repeated failures

Owner:
command_center

## Weekly Executive Review

Time: Sunday 7:00 PM.

Includes:

* Personal Operating System summary
* Master Venture Portfolio summary
* Command Center summary
* Career progress
* Engineering progress
* Venture pipeline movement
* Top risks
* Next week's priorities

Owner:
command_center

## Monthly Portfolio Review

Time: first Sunday of each month.

Includes:

* Venture rankings
* Kill/continue recommendations
* Revenue opportunities
* Resource allocation
* Strategic recommendations

Owner:
venture_portfolio with command_center review.

## Default Escalation Rules

* Critical blocker → immediate Telegram alert.
* Review-required task older than 24 hours → daily escalation.
* Failed worker run → command_center review.
* Repeated crashes → engineering_lab investigation.
* Revenue opportunity → venture_portfolio priority review.
