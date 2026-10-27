# Capture shapes

One JSON object per page read. Every capture has:

| field | needed | what |
| --- | --- | --- |
| `kind` | yes | `sub_search`, `sub_about`, `user_about`, `rules`, `listing`, `thread` or `profile` |
| `url` | yes | the reddit.com page you read |
| `items` | yes | a list, shapes below (empty is fine) |
| `pages` | no | page loads this took, default 1 (scrolling for more counts) |
| `blocked` | no | `true` if Reddit showed a captcha, a rate limit or any warning |
| `note` | no | what the block said, or anything odd about the page |

Fields not listed here are refused, so a typo shows up straight away. Usernames
may keep their `u/` and subs their `r/`; the tool strips them. Ages and dates
can be copied as shown: "5 hr. ago", "2d", "Created Jan 25, 2008",
"Oct 20, 2026" or an ISO date all work.

If a page shows a block or warning instead of content, do not write a capture.
Run `capture.py halt "<what it showed>"` instead (see BROWSER.md).

## sub_search

`reddit.com/search/?q=<topic>&type=communities`. Add `"query": "<topic>"`.

```json
{"kind": "sub_search", "url": "https://www.reddit.com/search/?q=espresso&type=communities",
 "query": "espresso",
 "items": [{"name": "r/espresso", "members": "1.2M members", "description": "All things espresso"}]}
```

## sub_about

`reddit.com/r/<sub>/`. One item.

```json
{"kind": "sub_about", "url": "https://www.reddit.com/r/espresso/",
 "items": [{"name": "espresso", "members": "1.2M", "weekly_visitors": "210K",
            "weekly_contributions": "4.5K", "created": "Created May 1, 2010", "description": "..."}]}
```

## user_about

The user's own `reddit.com/user/<name>/`. One item: karma and cake day as shown.

```json
{"kind": "user_about", "url": "https://www.reddit.com/user/quiet_brewer/",
 "items": [{"name": "quiet_brewer", "karma": "1,204", "created": "Oct 20, 2026"}]}
```

## rules

`old.reddit.com/r/<sub>/about/rules`, else the Rules box on the sub page. One item
per rule, in order, with the full text. Add `"sub"`.

```json
{"kind": "rules", "sub": "espresso", "url": "https://old.reddit.com/r/espresso/about/rules",
 "items": [{"title": "No AI-generated content", "text": "Posts or comments written by AI will be removed."}]}
```

If the sidebar or wiki has more rules (often on self-promotion), add them as more
items and say where they came from in `note`.

## listing

Your home feed, a sub's New tab or search results. `source` is `home`, `new`,
`hot`, `top`, `rising` or `search`. For search add `"query"`; for a sub add
`"sub"`.

```json
{"kind": "listing", "source": "new", "sub": "espresso", "url": "https://www.reddit.com/r/espresso/new/",
 "items": [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/first_shot_sour/",
            "title": "First shot is sour", "sub": "espresso", "author": "u/beanhead",
            "age": "5 hr. ago", "score": "12", "comments": "3 comments", "flair": "Help",
            "locked": false, "body": "first lines of the post, if shown"}]}
```

## thread

One thread page. `post` is the post, in the listing item shape, with the full
body. `items` are the comments you can see, top-level first.

```json
{"kind": "thread", "url": "https://www.reddit.com/r/espresso/comments/1abc2d/first_shot_sour/",
 "post": {"url": "https://www.reddit.com/r/espresso/comments/1abc2d/first_shot_sour/",
          "title": "First shot is sour", "sub": "espresso", "author": "beanhead",
          "age": "5h", "score": "12", "comments": "3", "body": "full text", "locked": false},
 "items": [{"author": "pro", "text": "Grind finer.", "score": "9", "age": "4h", "depth": 0}]}
```

## profile

The user's own `reddit.com/user/<name>/submitted/` or `/comments/` page. `type`
is `post` or `comment`. Set `removed` to `true` when Reddit labels the item as
removed (you see that label on your own posts when logged in).

```json
{"kind": "profile", "url": "https://www.reddit.com/user/me/comments/",
 "items": [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/kx9zz1/", "sub": "espresso",
            "type": "comment", "text": "grind finer", "score": "4", "comments": "1", "age": "2d",
            "removed": false}]}
```
