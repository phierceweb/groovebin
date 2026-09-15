# Security Policy

## Supported versions

The latest released version receives fixes. This is a small tool; older versions are not
back-patched.

## Reporting a vulnerability

Email **oss@phierceweb.com** with a description and, where possible, steps to reproduce.
Please do not open a public issue for a security report.

Expect an acknowledgement within a week. Once a fix ships, the release notes credit the
reporter unless anonymity is requested.

## Scope notes

groovebin reads and writes Standard MIDI Files and reads folders of them. It opens no network
connection and stores no credentials. Relevant classes of issue include:

- A crafted MIDI file that makes a read hang, exhaust memory, or write a file that differs
  from the intended edit.
- A path that makes a command write outside the output location it was given, or over its
  input.

MIDI files can carry song titles, names and other text in their meta events — treat them as
private data when attaching one to a report, and prefer a minimal reproduction.
