# Architecture notes

This document describes the public, high-level architecture only. It intentionally excludes production endpoints, collections, security rules, credentials and implementation details.

## Client

The Flutter application provides bilingual patient workflows for onboarding, check-ins, booking and monitoring. Client-side validation improves usability, while health-safety decisions remain behind authenticated server-side controls.

## Data and services

Firebase supports authentication and application data. REST APIs separate mobile presentation from business logic and external service integrations.

## Clinical workflow

AI-assisted features are bounded by server-side controls and designed to route appropriate cases into professional review. They do not independently diagnose, prescribe or replace medical care.

## Privacy boundary

The public repository contains only product documentation and approved screenshots. Production code and patient information remain private.
