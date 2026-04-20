# Step 5 — Corteva-Inspired Restyle

Goal: transform the current dark-gold theme into a Corteva-style light, agricultural-modern interface — Mariner blue primary, fresh green secondary, warm off-white backgrounds, serif display headings, big field imagery on the dashboard.

## Good news up front

Your current CSS is built on **CSS custom properties** (variables in `:root`). That means the restyle is 80% redefining variables, not rewriting every rule. You can drop the whole color palette with about 30 lines of CSS. The layout structure — sidebar, cards, stat blocks, alert rows — all keeps working.

The three bigger changes: (1) swap the display font, (2) flip shadows and borders because dark theme → light theme inverts contrast, (3) add a new hero block on the dashboard.

---

## The Corteva palette

Corteva's actual brand uses **Mariner blue** + **Black** as the logo colors, with a "clean and modern" aesthetic and "vibrant colors that symbolize growth and vitality." Their product categories are color-coded (herbicides green, fungicides purple, insecticides orange, etc.). For an app interface you want a more restrained two-or-three-color system pulled from that language.

Here's the palette to use — all hex codes derived from Corteva's published brand language and adjusted for readable web interfaces:

### Brand

| Token | Value | Use |
|---|---|---|
| `--mariner-900` | `#0F2845` | Sidebar background, deep headings |
| `--mariner-700` | `#1B3A5C` | Primary buttons, links, active nav |
| `--mariner-500` | `#3B6EB0` | Hover states, secondary accents |
| `--mariner-100` | `#E6EEF8` | Info backgrounds, selected rows |
| `--growth-600` | `#5C9029` | Success / primary CTA (agricultural green) |
| `--growth-500` | `#7FB83D` | Positive KPIs, available stock |
| `--growth-100` | `#ECF5DC` | Soft success backgrounds |

### Neutrals

| Token | Value | Use |
|---|---|---|
| `--cream` | `#FBFAF5` | Page background (warm off-white) |
| `--surface` | `#FFFFFF` | Card / panel background |
| `--surface-2` | `#F4F1E9` | Muted surface (table stripes, inputs) |
| `--border` | `#E6E1D3` | Card borders |
| `--border-2` | `#CFC8B4` | Stronger dividers |
| `--ink` | `#12181F` | Primary text |
| `--ink-2` | `#3D4A5C` | Secondary text |
| `--ink-3` | `#6F7B8B` | Muted / captions |

### Status

| Token | Value | Use |
|---|---|---|
| `--danger` | `#C83E3E` | Critical stock, overdue |
| `--danger-dim` | `#FBEAEA` | Danger backgrounds |
| `--warn` | `#D17825` | Warnings |
| `--warn-dim` | `#FCF0E3` | Warning backgrounds |
| `--success` | `var(--growth-600)` | Success indicators |
| `--success-dim` | `var(--growth-100)` | Success backgrounds |

---

## Typography

Corteva's website uses a clean geometric sans for body, with confident serif headlines on editorial surfaces. Your current stack has the right shape — Playfair Display serif + DM Sans — but Playfair is a bit fashion-editorial for an agriculture data app. Swap it for **Fraunces** (optical-sized, modern serif that still feels warm) and keep DM Sans for body.

### Font import (replaces the `<link>` on `base.html:9`)

**Before**:

```html
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=DM+Sans:wght@300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
```

**After**:

```html
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

JetBrains Mono replaces IBM Plex Mono (both work; JetBrains has slightly better legibility at 10px which the sidebar uses).

---

## Drop-in replacement for `:root`

Replace lines **12-37** of `base.html` (the entire `:root` block) with this:

```css
:root {
  /* ── Brand ─────────────────────────────────── */
  --mariner-900:  #0F2845;
  --mariner-700:  #1B3A5C;
  --mariner-500:  #3B6EB0;
  --mariner-100:  #E6EEF8;
  --growth-600:   #5C9029;
  --growth-500:   #7FB83D;
  --growth-100:   #ECF5DC;

  /* ── Neutrals ──────────────────────────────── */
  --cream:        #FBFAF5;
  --surface:      #FFFFFF;
  --surface-2:    #F4F1E9;
  --border:       #E6E1D3;
  --border-2:     #CFC8B4;
  --ink:          #12181F;
  --ink-2:        #3D4A5C;
  --ink-3:        #6F7B8B;

  /* ── Aliases for existing variable names ───── */
  /* (so the rest of the CSS doesn't need renaming) */
  --bg:           var(--cream);
  --sidebar:      var(--mariner-900);
  --text:         var(--ink);
  --text-2:       var(--ink-2);
  --text-3:       var(--ink-3);

  /* Primary accent was "gold" — now Mariner */
  --gold:         var(--mariner-700);
  --gold-dim:     var(--mariner-100);
  --gold-mid:     rgba(27,58,92,0.20);
  --gold-glow:    rgba(27,58,92,0.15);

  /* Semantic */
  --red:          #C83E3E;
  --red-dim:      #FBEAEA;
  --green:        var(--growth-600);
  --green-dim:    var(--growth-100);
  --amber:        #D17825;
  --amber-dim:    #FCF0E3;

  /* Shape & typography */
  --sidebar-w:    232px;
  --r:            8px;
  --r-lg:         14px;
  --shadow-sm:    0 1px 2px rgba(15,40,69,0.06);
  --shadow-md:    0 4px 12px rgba(15,40,69,0.08);
  --shadow-lg:    0 12px 32px rgba(15,40,69,0.10);

  --mono:         'JetBrains Mono', ui-monospace, monospace;
  --serif:        'Fraunces', Georgia, serif;
  --sans:         'DM Sans', system-ui, sans-serif;
}
```

The alias block at the bottom is what makes this a drop-in replacement — all your existing rules that reference `--bg`, `--text`, `--gold` etc. still work. They just point at Corteva colors now.

---

## Small light-theme cleanups

A few rules in the current CSS assume dark-on-dark and will look wrong on a light theme. Search `base.html` for each and adjust:

### Sidebar text (around line 97)

Sidebar stays dark (Mariner 900 background), so sidebar-specific text should be light. Most of the current sidebar styles reference `var(--text)` which now resolves to `--ink` (dark). Add these overrides at the end of the sidebar block in `base.html`:

```css
.sidebar { color: #E6EEF8; }
.sidebar-wordmark { color: #FFFFFF; }
.sidebar-farm-info { color: rgba(230,238,248,0.55); }
.nav-label { color: rgba(230,238,248,0.55); }
.nav-item { color: rgba(230,238,248,0.75); }
.nav-item:hover {
  color: #FFFFFF;
  background: rgba(255,255,255,0.06);
  border-left-color: rgba(255,255,255,0.15);
}
.nav-item.active {
  color: #FFFFFF;
  background: rgba(127,184,61,0.18);       /* growth-500 tint */
  border-left-color: var(--growth-500);
}
.nav-item.active svg { color: var(--growth-500); }
.sidebar-icon {
  background: rgba(127,184,61,0.15);
  border-color: rgba(127,184,61,0.4);
  color: var(--growth-500);
}
.system-status { color: rgba(230,238,248,0.55); }
.user-name { color: #FFFFFF; }
.user-meta { color: rgba(230,238,248,0.45); }
.sidebar-brand, .sidebar-footer { border-color: rgba(255,255,255,0.08); }
```

### Main surface shadows

Add shadows to cards and panels — a dark theme doesn't need them but a light theme does. Find `.section` (or whatever class wraps your dashboard cards, search for "section {" in base.html) and add:

```css
.section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-sm);
  padding: 24px;
}
```

Stat blocks get the same treatment:

```css
.stat-block {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--r-lg);
  box-shadow: var(--shadow-sm);
  padding: 20px;
}
```

### Primary button (`.btn-new-log`, line 177)

Swap the gold fill for growth-green and adjust the hover:

**Before**:

```css
.btn-new-log {
  /* ... */
  background: var(--gold);
  color: #fff;
}
.btn-new-log:hover {
  background: #B5842F;
  box-shadow: 0 4px 20px var(--gold-glow);
}
```

**After**:

```css
.btn-new-log {
  /* ... */
  background: var(--growth-600);
  color: #fff;
  box-shadow: 0 2px 8px rgba(92,144,41,0.30);
}
.btn-new-log:hover {
  background: var(--growth-500);
  box-shadow: 0 4px 16px rgba(92,144,41,0.40);
}
```

---

## Dashboard hero section

The dashboard is your audience view, so it deserves a proper hero. Insert this block **at the top of `dashboard.html`**, right after `{% block content %}` and **before** the existing `<div class="page-header">`:

```jinja
<div class="hero">
  <div class="hero-image">
    <img src="https://images.unsplash.com/photo-1625246333195-78d9c38ad449?auto=format&fit=crop&w=1600&q=80"
         alt="Cornfield at sunrise">
    <div class="hero-overlay"></div>
  </div>
  <div class="hero-content">
    <div class="hero-eyebrow">{{ farm.name if farm else 'Research Farm' }}</div>
    <h1 class="hero-title">Growing what's next.</h1>
    <p class="hero-sub">
      {% if today_logs %}
        {{ today_logs | length }} usage event{{ 's' if today_logs|length != 1 else '' }} logged today.
      {% else %}
        No usage logged today — start tracking from the sidebar.
      {% endif %}
      {% if critical_count %}
        <span class="hero-alert">{{ critical_count }} item{{ 's' if critical_count != 1 else '' }} critically low.</span>
      {% endif %}
    </p>
    <div class="hero-actions">
      <a href="{{ url_for('log_usage') }}" class="hero-btn hero-btn-primary">Log usage</a>
      <a href="{{ url_for('suggestions') }}" class="hero-btn hero-btn-ghost">View reorder suggestions →</a>
    </div>
  </div>
</div>
```

Then add this CSS block **at the end of the `<style>` tag in `base.html`** (before `</style>`):

```css
/* ── HERO ───────────────────────────────────── */
.hero {
  position: relative;
  border-radius: var(--r-lg);
  overflow: hidden;
  margin-bottom: 32px;
  min-height: 340px;
  box-shadow: var(--shadow-md);
}

.hero-image { position: absolute; inset: 0; }
.hero-image img {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
}

.hero-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(
    100deg,
    rgba(15,40,69,0.85) 0%,
    rgba(15,40,69,0.60) 45%,
    rgba(15,40,69,0.15) 100%
  );
}

.hero-content {
  position: relative;
  padding: 56px 48px;
  max-width: 640px;
  color: #FFFFFF;
}

.hero-eyebrow {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--growth-500);
  margin-bottom: 14px;
}

.hero-title {
  font-family: var(--serif);
  font-weight: 600;
  font-size: 52px;
  line-height: 1.05;
  letter-spacing: -0.02em;
  margin-bottom: 18px;
}

.hero-sub {
  font-size: 16px;
  font-weight: 400;
  line-height: 1.55;
  color: rgba(255,255,255,0.88);
  margin-bottom: 28px;
  max-width: 520px;
}

.hero-alert {
  display: inline-block;
  margin-left: 4px;
  padding: 2px 10px;
  background: rgba(200,62,62,0.25);
  border: 1px solid rgba(200,62,62,0.45);
  border-radius: 4px;
  font-size: 13px;
  color: #FFD5D5;
}

.hero-actions { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }

.hero-btn {
  display: inline-flex;
  align-items: center;
  padding: 13px 26px;
  border-radius: var(--r);
  font-weight: 600;
  font-size: 14px;
  letter-spacing: 0.01em;
  transition: transform 120ms, box-shadow 120ms, background 120ms;
  cursor: pointer;
}

.hero-btn-primary {
  background: var(--growth-600);
  color: #FFFFFF;
  box-shadow: 0 4px 14px rgba(92,144,41,0.45);
}
.hero-btn-primary:hover {
  background: var(--growth-500);
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(92,144,41,0.55);
}

.hero-btn-ghost {
  color: rgba(255,255,255,0.92);
  border: 1px solid rgba(255,255,255,0.35);
}
.hero-btn-ghost:hover {
  background: rgba(255,255,255,0.12);
  border-color: rgba(255,255,255,0.55);
}

@media (max-width: 900px) {
  .hero-content { padding: 36px 28px; }
  .hero-title { font-size: 36px; }
}
```

---

## Imagery — free, license-safe sources

The hero image above is a direct Unsplash URL — free to use, no attribution legally required (though courtesy is nice). Here are three alternatives for the dashboard and other pages; swap by changing the `src` attribute.

| Use | URL | Description |
|---|---|---|
| Dashboard hero (default) | `https://images.unsplash.com/photo-1625246333195-78d9c38ad449?auto=format&fit=crop&w=1600&q=80` | Cornfield at sunrise, warm tones |
| Dashboard hero alt | `https://images.unsplash.com/photo-1560493676-04071c5f467b?auto=format&fit=crop&w=1600&q=80` | Green crop rows from above |
| Dashboard hero alt 2 | `https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&w=1600&q=80` | Farmer walking through wheat, golden hour |
| Login page background | `https://images.unsplash.com/photo-1535090042247-30731e4d4b57?auto=format&fit=crop&w=1600&q=80` | Wide-angle field at dusk |
| Inventory page banner (optional) | `https://images.unsplash.com/photo-1625246333195-78d9c38ad449?auto=format&fit=crop&w=1600&q=80` | Reuse hero image |

Unsplash serves optimized images through the `?auto=format&fit=crop&w=<N>` query params — no local storage needed, always fast. If your organization requires all assets to be served locally, download each image once and place in `static/images/`, then change the `src` to `{{ url_for('static', filename='images/hero-field.jpg') }}`.

---

## Login page treatment

Give the login page a split-screen: photo on the left, form on the right. Find the wrapper in `login.html` (likely a `<div class="login-page">` or similar) and restructure. The quickest version — add this at the top of `login.html` if your existing markup isn't easy to modify:

```jinja
{% block extra_head %}
<style>
  body { background: var(--cream); }
  .login-split {
    display: grid;
    grid-template-columns: 1fr 480px;
    min-height: 100vh;
  }
  .login-split-image {
    background:
      linear-gradient(180deg, rgba(15,40,69,0.25), rgba(15,40,69,0.55)),
      url('https://images.unsplash.com/photo-1535090042247-30731e4d4b57?auto=format&fit=crop&w=1600&q=80') center/cover;
    display: flex;
    align-items: flex-end;
    padding: 60px;
  }
  .login-split-image-text {
    color: #FFFFFF;
    font-family: var(--serif);
    font-size: 32px;
    font-weight: 600;
    line-height: 1.15;
    max-width: 420px;
  }
  .login-split-form {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 40px;
    background: var(--surface);
  }
  @media (max-width: 900px) {
    .login-split { grid-template-columns: 1fr; }
    .login-split-image { min-height: 240px; }
  }
</style>
{% endblock %}
```

Then wrap the existing login form body with:

```jinja
<div class="login-split">
  <div class="login-split-image">
    <div class="login-split-image-text">
      Precision research. Shared infrastructure. One farm of record.
    </div>
  </div>
  <div class="login-split-form">
    <!-- existing login form markup goes here -->
  </div>
</div>
```

---

## Apply order (what to paste, and when)

1. **Replace the font import** on `base.html:9`. Hard refresh the browser — type should change immediately.
2. **Replace the `:root` block** at `base.html:12-37` with the new one. The whole app should flip to light-on-cream with blue accents.
3. **Add the sidebar-light overrides** — paste the block under the existing sidebar CSS rules in `base.html`. Sidebar text goes light-on-dark-blue correctly.
4. **Add the surface shadow adjustments** — update `.section` and `.stat-block` rules in `base.html`. Cards lift off the cream background.
5. **Swap the `.btn-new-log` colors** — primary action in sidebar becomes green.
6. **Add the hero CSS block** at the end of base.html's `<style>`.
7. **Insert the hero markup** at the top of `dashboard.html`.
8. **(Optional) Restyle the login page** per the login section above.

Each step is independently testable — if something looks wrong after step 3, you can roll back just that step's paste.

---

## Verify

After each step, do a hard refresh (`Cmd+Shift+R`). Walk through:

- Dashboard: big hero banner with field photo, "Growing what's next" in serif, green CTA button, sidebar dark blue with green highlight on the active item.
- Sidebar: wordmark readable in white against Mariner blue background, active nav has green left-border.
- Stat strip: five white cards with subtle shadow, color-coded numbers unchanged (just now on a cream page instead of black).
- Inventory: table still legible, Delete/Edit buttons still styled correctly.
- Log and treatments: forms render on cream, inputs have subtle borders.
- Suggestions: urgency cards (critical/warning/info) still distinguishable.

Quick sanity check from terminal:

```bash
python server.py &
sleep 2
# Pull the HTML and confirm the new CSS is being served
curl -s http://127.0.0.1:5001/login | grep -c "mariner-900"
# Expected: 1 or more (the CSS block is loading)
kill %1
```

---

## What this buys you

Before: dark moody theme, gold accents, looks more like a wine-store POS than an agriculture platform. Fine for a dev demo, not for a stakeholder demo.

After: Mariner blue + agricultural green on cream, serif headlines, big field hero on the dashboard, clean cards with soft shadows. Looks like something a serious ag-research institution actually built — which is what you're trying to signal.

Still to do if you want to push the design further: restyle the tables with zebra-striping and more generous row-padding, add a footer with institutional branding, add variety-color coding on the plot views (corn = yellow, soy = muted-green), introduce subtle fade-in animations on card mount. All optional polish — none of it blocks shipping.
