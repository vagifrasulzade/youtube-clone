import { useQuery } from '@tanstack/react-query'
import { useId, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router'

import { getJson } from '../../api/http'
import { useDebounced } from '../../hooks/useDebounced'
import { SearchIcon } from '../icons'

/** Header search with server-side title suggestions (keyboard accessible combobox). */
export function SearchBox() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [query, setQuery] = useState(params.get('search_query') ?? '')
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const listId = useId()
  const term = useDebounced(query.trim(), 200)

  const suggestions = useQuery({
    queryKey: ['suggestions', term],
    queryFn: () => getJson<string[]>('/search/suggestions', { q: term }),
    enabled: open && term.length > 0,
    staleTime: 60_000,
  })
  const items = open && term ? (suggestions.data ?? []) : []

  function go(value: string) {
    const q = value.trim()
    if (!q) return
    setQuery(q)
    setOpen(false)
    setActive(-1)
    navigate(`/results?search_query=${encodeURIComponent(q)}`)
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    go(active >= 0 && items[active] ? items[active] : query)
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown' && items.length > 0) {
      event.preventDefault()
      setActive((i) => (i + 1) % items.length)
    } else if (event.key === 'ArrowUp' && items.length > 0) {
      event.preventDefault()
      setActive((i) => (i <= 0 ? items.length - 1 : i - 1))
    } else if (event.key === 'Escape') {
      setOpen(false)
      setActive(-1)
    }
  }

  return (
    <form onSubmit={submit} role="search" className="relative flex max-w-[640px] flex-1 items-center">
      <input
        type="search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
          setActive(-1)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={onKeyDown}
        placeholder="Search"
        aria-label="Search"
        role="combobox"
        aria-expanded={items.length > 0}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        maxLength={100}
        autoComplete="off"
        className="h-10 w-full min-w-0 rounded-l-full border border-yt-border px-4 text-base outline-none focus:border-yt-blue"
      />
      <button
        type="submit"
        aria-label="Search"
        className="flex h-10 w-16 shrink-0 items-center justify-center rounded-r-full border border-l-0 border-yt-border bg-[#f8f8f8] hover:bg-yt-active"
      >
        <SearchIcon size={22} />
      </button>

      {items.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute left-0 right-16 top-11 z-40 overflow-hidden rounded-xl bg-yt-bg py-3 shadow-[0_4px_32px_rgba(0,0,0,0.1)]"
        >
          {items.map((item, index) => (
            <li
              key={item}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              // mousedown (not click) fires before the input's blur closes the list
              onMouseDown={(e) => {
                e.preventDefault()
                go(item)
              }}
              className={`flex cursor-default items-center gap-4 px-4 py-1.5 text-base font-medium ${
                index === active ? 'bg-yt-hover' : 'hover:bg-yt-hover'
              }`}
            >
              <SearchIcon size={18} />
              <span className="truncate">{item}</span>
            </li>
          ))}
        </ul>
      )}
    </form>
  )
}
