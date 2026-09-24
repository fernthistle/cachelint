# cachelint

A validating parser and pretty printer for the HTTP `Cache-Control` header.

The header's grammar is small (a comma-separated list of tokens, some with
arguments) but the rules for what's actually *valid* depend on details that
are easy to get wrong by hand:

- `max-age` requires a delta-seconds argument; `max-stale` doesn't require one.
- `no-cache` and `private` can carry an optional quoted list of field names,
  but only on a response. On a request, `no-cache` is a bare flag.
- Several directives (`public`, `must-revalidate`, `s-maxage`, ...) are only
  meaningful on a response; others (`only-if-cached`, `min-fresh`) only make
  sense on a request. A header that's syntactically fine can still be nonsense
  for the side of the exchange it showed up on.
- Repeated directives, non-numeric delta-seconds, and unquoted field-name
  lists are all things real servers and proxies emit by mistake.

`cachelint` parses a header value, checks it against RFC 9111 (plus the
`stale-while-revalidate` / `stale-if-error` extensions from RFC 5861), and
reports errors and warnings alongside a structured breakdown of the
directives it found.

No third-party dependencies - standard library only.

## Usage

As a library:

```python
from cachelint import parse_cache_control, format_result

result = parse_cache_control(
    'max-age=3600, must-revalidate, private="Set-Cookie"',
    context="response",
)
print(format_result(result))
```

```
Cache-Control (response):
  max-age = 3600
  must-revalidate
  private -> fields: Set-Cookie
valid, no issues found
```

Something invalid:

```python
result = parse_cache_control("max-age=oops, max-age=60, only-if-cached", context="response")
print(format_result(result))
```

```
Cache-Control (response):
  max-age = oops
  max-age = 60
  only-if-cached
errors:
  - 'max-age' argument 'oops' is not a non-negative integer
warnings:
  - directive 'max-age' repeated
  - 'only-if-cached' has no defined meaning in a response header
```

From the command line:

```console
$ python -m cachelint.cli "no-store, no-transform" --context response
Cache-Control (response):
  no-store
  no-transform
valid, no issues found
```

And with `--json`, for feeding into other tooling:

```console
$ python -m cachelint.cli "max-age=3600, stale-while-revalidate=30" --json
{
  "context": "response",
  "valid": true,
  "directives": [
    {
      "name": "max-age",
      "argument": "3600",
      "field_names": null
    },
    {
      "name": "stale-while-revalidate",
      "argument": "30",
      "field_names": null
    }
  ],
  "issues": []
}
```

The exit code is `1` if the header has any errors, `0` otherwise (warnings
don't affect the exit code).

If no header value is given as an argument, `cachelint` reads it from stdin,
so it composes with `curl -sI` and similar:

```console
$ curl -sI https://example.com | grep -i ^cache-control: | cut -d' ' -f2- | python -m cachelint.cli --json
```

### Expires and Age

`Expires` is an HTTP-date; `Age` is a delta-seconds integer. Both are handled
by the same library and CLI, selected with `--header`:

```python
from cachelint import parse_expires, format_expires

result = parse_expires("Sun, 06 Nov 1994 08:49:37 GMT")
print(format_expires(result))
```

```
Expires: 'Sun, 06 Nov 1994 08:49:37 GMT'
  parsed: 1994-11-06T08:49:37+00:00
  expired: True
```

Per RFC 9111 5.3, a date that doesn't parse - including the legacy value
`"0"` - is treated as already expired rather than as an error:

```console
$ python -m cachelint.cli --header expires "not a date"
Expires: 'not a date'
  expired: True
  warning: 'not a date' is not a valid HTTP-date; treating as already expired per RFC 9111 5.3
```

`Age` follows the same delta-seconds rules as `max-age`, including the
2**31-1 clamp from RFC 9111 1.2.2 for values a sender failed to bound:

```console
$ python -m cachelint.cli --header age 120
Age: '120'
  seconds: 120
```

## Scope right now

`Cache-Control`, `Expires`, and `Age` are handled. `Vary` and `ETag` have
their own parsing and validation quirks and are planned but not implemented
yet, and nothing yet combines multiple headers from the same message into
one report.

## License

MIT, see [LICENSE](LICENSE).
