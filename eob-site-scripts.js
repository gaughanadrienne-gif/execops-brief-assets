/* ==========================================================================
   The Exec Ops Brief - site-wide behavior layer  (eob-site-scripts.js)
   --------------------------------------------------------------------------
   The EOB equivalent of Ambitious Harvest's ah-site-scripts.js.
   Hosted in the execops-brief-assets GitHub repo, served via jsDelivr, and
   loaded once from Squarespace  ->  Settings  ->  Advanced  ->  Code Injection
   -> HEADER with:

     <script defer src="https://cdn.jsdelivr.net/gh/gaughanadrienne-gif/execops-brief-assets@main/eob-site-scripts.js"></script>

   After any edit: git commit + push, then purge the CDN so the change is live:
     curl -s "https://purge.jsdelivr.net/gh/gaughanadrienne-gif/execops-brief-assets@main/eob-site-scripts.js"

   Modules (all idempotent; 1-3 article-only, 4 shop-only):
     1. Keep Reading   - related-article cards from the embedded manifest
     2. FAQ polish     - consistent styling for the FAQ block
     3. Callouts       - keyword-routed product / referral callout, mid-article
     3b. Tool callouts - SEPARATE slot routing readers into the 4 free tools.
                         Injects at a late heading so it can coexist with the
                         module-3 box on the same article without displacing it.
     4. Shop polish    - Design System v2 styling for the NATIVE store pages
                         (list masthead + typography, oxblood cart button,
                         uncropped gallery, collapses empty leftover sections)

   IMPORTANT: the DOM selectors below target a standard Squarespace 7.1 blog
   post. Smoke-test on the live site once and adjust CONTENT_SELECTORS if the
   template differs. Nothing here mutates data; it only injects UI.
   Voice rule: no em-dashes, no emojis in any injected copy.
   ========================================================================== */
(function () {
  'use strict';

  var CFG = {
    blogBase: '/library/',        // article URL prefix on the live site
    maxRelated: 3,
    brand: {
      paper:  '#F3F0E9',
      ink:    '#1B1712',
      navy:   '#1C2C3A',
      oxblood:'#7A2129',
      slate:  '#5A5348',
      rule:   '#DED7C7'
    }
  };

  // --- Article manifest (slug, title, pillar). Keep in sync as articles ship.
  var ARTICLES = [
    {s:'what-does-a-chief-of-staff-do', t:'What Does a Chief of Staff Actually Do?', p:'The Role, Defined'},
    {s:'chief-of-staff-vs-executive-assistant-vs-coo', t:'Chief of Staff vs. Executive Assistant vs. COO', p:'The Role, Defined'},
    {s:'three-types-of-chief-of-staff', t:'The Three Types of Chief of Staff', p:'The Role, Defined'},
    {s:'day-in-the-life-chief-of-staff', t:'A Day in the Life of a Chief of Staff', p:'The Role, Defined'},
    {s:'what-an-executive-assistant-to-a-ceo-does', t:'What an Executive Assistant to a CEO Actually Does', p:'The Role, Defined'},
    {s:'chief-of-staff-founder-vs-established-ceo', t:'Chief of Staff to a Founder vs. an Established CEO', p:'The Role, Defined'},
    {s:'when-does-a-company-need-a-chief-of-staff', t:'When Does a Company Actually Need a Chief of Staff?', p:'The Role, Defined'},
    {s:'ea-to-chief-of-staff-path', t:'The EA-to-Chief-of-Staff Path', p:'The Path In'},
    {s:'chief-of-staff-certifications-compared', t:'Chief of Staff Certifications and Courses, Compared', p:'The Path In'},
    {s:'skills-to-get-hired-as-chief-of-staff', t:'The Skills That Actually Get You Hired', p:'The Path In'},
    {s:'resume-linkedin-for-exec-ops', t:'Position Your Resume and LinkedIn for Exec-Ops Roles', p:'The Path In'},
    {s:'land-first-chief-of-staff-role-without-the-title', t:'Land Your First Chief of Staff Role Without the Title', p:'The Path In'},
    {s:'breaking-into-chief-of-staff-from-consulting-or-finance', t:'Breaking Into Chief of Staff From Consulting or Finance', p:'The Path In'},
    {s:'run-effective-leadership-team-meeting', t:'How to Run an Effective Leadership Team Meeting', p:'The Craft / Playbooks'},
    {s:'first-90-days-chief-of-staff-operating-plan', t:'The First 90 Days as a Chief of Staff', p:'The Craft / Playbooks'},
    {s:'managing-up-chief-of-staff', t:'Managing Up: Make Your Principal More Effective', p:'The Craft / Playbooks'},
    {s:'single-source-of-truth-decision-logs', t:'Building a Single Source of Truth', p:'The Craft / Playbooks'},
    {s:'how-to-build-an-operating-cadence', t:'How to Build an Operating Cadence', p:'The Craft / Playbooks'},
    {s:'board-meeting-prep-chief-of-staff', t:'Board Meeting Prep: The Playbook', p:'The Craft / Playbooks'},
    {s:'prioritization-frameworks-for-operators', t:'Prioritization Frameworks Every Operator Should Know', p:'The Craft / Playbooks'},
    {s:'how-to-write-an-executive-memo', t:'How to Write an Executive Memo That Gets Read', p:'The Craft / Playbooks'},
    {s:'leading-cross-functional-projects-without-authority', t:'Leading Cross-Functional Projects Without Authority', p:'The Craft / Playbooks'},
    {s:'building-and-running-an-okr-process', t:'Building and Running an OKR Process', p:'The Craft / Playbooks'},
    {s:'protecting-an-executives-time-and-focus', t:'How Great Operators Protect an Executive’s Time', p:'The Craft / Playbooks'},
    {s:'gatekeeping-well-saying-no-for-your-principal', t:'Gatekeeping Well: Say No for Your Principal', p:'The Craft / Playbooks'},
    {s:'chief-of-staff-salary-guide', t:'Chief of Staff Salary Guide', p:'Comp & Careers'},
    {s:'negotiate-chief-of-staff-offer', t:'How to Negotiate a Chief of Staff Offer', p:'Comp & Careers'},
    {s:'fractional-vs-full-time-chief-of-staff', t:'Fractional vs. Full-Time Chief of Staff', p:'Comp & Careers'},
    {s:'how-to-read-exec-ops-job-post', t:'How to Read a $150k+ Exec-Ops Job Post', p:'Comp & Careers'},
    {s:'equity-for-chiefs-of-staff', t:'Equity for Chiefs of Staff', p:'Comp & Careers'},
    {s:'chief-of-staff-exit-paths', t:'Chief of Staff Exit Paths: What Operators Do Next', p:'The Career'},
    {s:'influence-without-authority', t:'Influence Without Authority', p:'Operator Mindset'},
    {s:'what-is-a-force-multiplier', t:'What It Means to Be a Force Multiplier', p:'Operator Mindset'},
    {s:'avoiding-burnout-operations-role', t:'Avoiding Burnout in a High-Intensity Operations Role', p:'Operator Mindset'},
    {s:'the-trust-equation', t:'The Trust Equation', p:'Operator Mindset'},
    {s:'how-to-become-a-chief-of-staff', t:'How to Become a Chief of Staff', p:'The Path In'},
    {s:'chief-of-staff-interview-questions', t:'Chief of Staff Interview Questions', p:'The Path In'},
    {s:'do-you-need-an-mba-to-be-a-chief-of-staff', t:'Do You Need an MBA to Be a Chief of Staff?', p:'The Path In'},
    {s:'how-to-create-a-chief-of-staff-role', t:'How to Create a Chief of Staff Role', p:'The Path In'},
    {s:'how-to-become-a-fractional-chief-of-staff', t:'How to Become a Fractional Chief of Staff', p:'The Role, Defined'},
    {s:'will-ai-replace-executive-assistants', t:'Will AI Replace Executive Assistants?', p:'The Role, Defined'},
    {s:'executive-assistant-salary-and-how-to-get-a-raise', t:'Executive Assistant Salary and How to Get a Raise', p:'Comp & Careers'},
    {s:'how-to-grow-your-career-as-an-executive-assistant', t:'How to Grow Your Career as an Executive Assistant', p:'The Path In'}
  ];

  /* Keyword-routed callouts (copy from Commercialization/Affiliate_Program_Plan.md).
     Each: { match:[substrings tested against slug+title], title, body, cta, href }.
     A callout stays DORMANT until its href is a real URL: any href still holding
     the REPLACE_WITH token is skipped, so this is safe to ship before programs are
     joined. First live match wins. To activate one: join the program, then paste
     the real affiliate URL over the token. Nova is already live. */
  var CALLOUTS = [
    { match:['chief-of-staff-certifications-compared','land-first-chief-of-staff-role-without-the-title','ea-to-chief-of-staff-path','certification','credential'],
      title:'If you want a structured way into the role, Nova is the course we point people to',
      body:'Most people learn the craft on the job, but a focused certification shortens the ramp and gives you language for interviews. Nova is the most established option, and Brief readers get $100 off.',
      cta:'See the Nova Chief of Staff course',
      href:'https://novachiefofstaff.mykajabi.com/a/2147831554/z9P6cao2' },
    { match:['how-to-build-an-operating-cadence','single-source-of-truth-decision-logs','operating cadence','source of truth'],
      title:'A cadence only holds if it lives somewhere the whole team can see',
      body:'The operators who keep decisions from getting relitigated run their cadence and their source of truth in one shared system, not a scatter of docs.',
      cta:'See the tool many operators run their cadence in',
      href:'REPLACE_WITH_CLICKUP_AFFILIATE_URL' },
    { match:['skills-to-get-hired-as-chief-of-staff','upskill'],
      title:'Close the specific gap, not "learn everything"',
      body:'The fastest way into an exec-ops seat is to fix the one or two gaps a hiring manager will probe, often finance fluency or structured project management. A targeted course is cheaper than waiting for the job to teach you.',
      cta:'Browse courses for the exec-ops skill set',
      href:'REPLACE_WITH_COURSERA_AFFILIATE_URL' },
    { match:['how-to-write-an-executive-memo','managing-up-chief-of-staff','board-meeting-prep-chief-of-staff','executive memo'],
      title:'In this role, your writing is the room’s read on your judgment',
      body:'A memo that is tight and clean gets decisions made; one that is not gets questioned. A second set of eyes on tone and clarity is cheap insurance on documents executives actually read.',
      cta:'See the writing tool for high-stakes documents',
      href:'REPLACE_WITH_GRAMMARLY_AFFILIATE_URL' },
    { match:['breaking-into-chief-of-staff-from-consulting-or-finance','cohort'],
      title:'If you learn better with a cohort, that route exists too',
      body:'Some people close the gap faster in a live cohort with peers and direct instructor feedback than they do alone. Maven hosts operator-taught courses on the exact skills this transition asks for.',
      cta:'See cohort courses for operators',
      href:'REPLACE_WITH_MAVEN_AFFILIATE_URL' },
    { match:['what-does-a-chief-of-staff-do','the-trust-equation','what-is-a-force-multiplier'],
      title:'The short shelf worth actually reading',
      body:'A handful of books cover most of what the role asks of you, from earning trust to running priorities. Start with the ones operators keep coming back to.',
      cta:'See the exec-ops reading list',
      href:'REPLACE_WITH_AMAZON_AFFILIATE_URL' },
    /* Free Notion template callouts (internal, always live). Kept BELOW the
       affiliate entries so an affiliate placement wins once its URL goes live. */
    { match:['single-source-of-truth-decision-logs','how-to-build-an-operating-cadence','run-effective-leadership-team-meeting'],
      title:'The decision log this playbook describes exists as a free Notion template',
      body:'A running record of what was decided, who owns it, why, and when to revisit. Ours ships with the full field schema and seeded examples, ready to duplicate into your workspace.',
      cta:'Get the free Decision Log template',
      href:'/resources#notion-templates' },
    { match:['managing-up-chief-of-staff','protecting-an-executives-time-and-focus','prioritization-frameworks-for-operators'],
      title:'The weekly brief is a free Notion template',
      body:'A live board for the one-page brief your principal actually reads: priorities, flags, what needs them, and a lightweight archive of past weeks.',
      cta:'Get the free Weekly Priorities template',
      href:'/resources#notion-templates' },
    { match:['first-90-days-chief-of-staff-operating-plan'],
      title:'Work this plan as a live tracker, not a printout',
      body:'The full 30/60/90 plan is a free Notion template with every focus item, artifact, and milestone pre-loaded. Set dates against your start date and work the board.',
      cta:'Get the free First 90 Days tracker',
      href:'/resources#notion-templates' },
    { match:['chief-of-staff-interview-questions','how-to-become-a-chief-of-staff','how-to-read-exec-ops-job-post','resume-linkedin-for-exec-ops'],
      title:'Running a search? Track it like an operator',
      body:'Our free Notion Job Search Tracker is a light pipeline: every role, its stage, the comp on the table, and the single next step that keeps it moving.',
      cta:'Get the free Job Search Tracker',
      href:'/resources#notion-templates' }
  ];

  /* Tool callouts (module 3b). SEPARATE SLOT from CALLOUTS above, so an article
     can carry BOTH a product/affiliate callout and a tool callout without one
     displacing the other. Rules:
       - max ONE tool callout per article; first match in this array wins
       - match on EXACT slugs only (no fuzzy keywords), so a new article can
         never pick one up by accident
       - rendered at a LATE anchor (see toolCallout) while the CALLOUTS box sits
         after the 2nd H2, so the two boxes never land next to each other
     Every claim here must be true of the tool as it actually ships in
     execops-brief-assets/tools/. Voice: no em-dashes, no emojis, no hype. */
  var TOOL_CALLOUTS = [
    /* ---- Offer evaluator (/offer-evaluator) ---- */
    { match:['negotiate-chief-of-staff-offer','fractional-vs-full-time-chief-of-staff'],
      title:'If you are holding a real offer, score it before you answer',
      body:'The offer evaluator compares base with a named current source, separates guaranteed cash from target cash, checks equity information readiness, and identifies the terms and questions still open.',
      cta:'Open the offer evaluator',
      href:'/offer-evaluator' },
    { match:['equity-for-chiefs-of-staff'],
      title:'Run the actual grant through the evaluator',
      body:'Equity is where offers stay vague. The evaluator does not treat private equity as cash or assign it a market grade. It checks whether you have ownership or fully diluted shares, strike price, the latest 409A and date, vesting, and the exercise window.',
      cta:'Open the offer evaluator',
      href:'/offer-evaluator' },

    /* ---- Salary and comp benchmarker (/salary-benchmarker) ---- */
    { match:['how-to-read-exec-ops-job-post'],
      title:'The post gives you a range. Here is what the seat actually pays.',
      body:'Before you answer a recruiter’s comp question, run the role through the benchmarker. It shows named role-relevant sources and keeps broad employer pay, incumbent surveys, and premium postings separate.',
      cta:'Open the salary benchmarker',
      href:'/salary-benchmarker' },
    { match:['chief-of-staff-salary-guide','executive-assistant-salary-and-how-to-get-a-raise'],
      title:'Get the number for your seat, not the national average',
      body:'The benchmarker shows role-specific source cards, including observed company-stage medians for Chiefs of Staff and distinct broad, incumbent, and premium comparisons for EAs. Sources, populations, and limitations are cited in the tool.',
      cta:'Open the salary benchmarker',
      href:'/salary-benchmarker' },
    { match:['how-to-create-a-chief-of-staff-role','how-to-become-a-fractional-chief-of-staff'],
      title:'Put a real number on the seat',
      body:'Whether you are pitching this role internally or pricing your own time against it, start with named comparisons. The benchmarker shows what each source measures without manufacturing a universal role, location, or experience multiplier.',
      cta:'Open the salary benchmarker',
      href:'/salary-benchmarker' },

    /* ---- Readiness quiz (/readiness-quiz) ---- */
    { match:['chief-of-staff-interview-questions'],
      title:'An interview loop probes six things. Find your soft spot first.',
      body:'The readiness quiz scores you across the six competencies the role is really hiring for and tells you which ones your evidence is thinnest on. Twelve questions, and you get a breakdown per dimension.',
      cta:'Take the readiness quiz',
      href:'/readiness-quiz' },
    { match:['how-to-become-a-chief-of-staff','skills-to-get-hired-as-chief-of-staff',
             'ea-to-chief-of-staff-path','chief-of-staff-certifications-compared',
             'land-first-chief-of-staff-role-without-the-title',
             'breaking-into-chief-of-staff-from-consulting-or-finance',
             'do-you-need-an-mba-to-be-a-chief-of-staff',
             'how-to-grow-your-career-as-an-executive-assistant'],
      title:'Before you plan the next move, find out where you actually stand',
      body:'The readiness quiz is twelve questions across the six competencies that separate people who thrive in this seat from people who struggle. You get a score for each one and a short list of the dimensions where your evidence is still thin.',
      cta:'Take the readiness quiz',
      href:'/readiness-quiz' },
    { match:['what-does-a-chief-of-staff-do','chief-of-staff-vs-executive-assistant-vs-coo',
             'day-in-the-life-chief-of-staff','will-ai-replace-executive-assistants'],
      title:'So is this you?',
      body:'Twelve questions, six competencies, and an honest read on how ready you are for the seat today. You will get a score for each dimension and the two or three worth working on first.',
      cta:'Take the readiness quiz',
      href:'/readiness-quiz' },

    /* ---- First 90 days plan (/first-90-days) ---- */
    { match:['first-90-days-chief-of-staff-operating-plan'],
      title:'Build your version of this plan, dated to your start',
      body:'The First 90 Days tool turns this playbook into a working checklist: before day one, days 1 to 30, 31 to 60, and 61 to 90, with the principal-alignment checks built into each phase. Tick items off in the browser and print the plan. No account needed.',
      cta:'Open the First 90 Days tool',
      href:'/first-90-days' },
    { match:['managing-up-chief-of-staff','how-to-build-an-operating-cadence'],
      title:'The alignment conversation has a checklist',
      body:'Our free First 90 Days tool carries the principal-alignment checks for week one, day 30, and day 60: what success means, what you own outright, what you can decide without asking. Work it as a checklist and print it.',
      cta:'Open the First 90 Days tool',
      href:'/first-90-days' }
  ];

  // ---- helpers -----------------------------------------------------------
  function currentSlug() {
    // path-agnostic: last URL segment; run() confirms it is a known article, so
    // this works whether articles are served at /library/, /learn/, or elsewhere.
    var p = location.pathname.replace(/\/+$/, '');
    return p.substring(p.lastIndexOf('/') + 1) || null;
  }
  function currentBase() {
    var p = location.pathname.replace(/\/+$/, '');
    return p.substring(0, p.lastIndexOf('/') + 1);
  }
  function findArticle(slug){
    for (var k=0;k<ARTICLES.length;k++){ if(ARTICLES[k].s===slug) return ARTICLES[k]; }
    return null;
  }
  function byId(id){ return document.getElementById(id); }
  function el(tag, css, html){
    var e = document.createElement(tag);
    if (css) e.style.cssText = css;
    if (html != null) e.innerHTML = html;
    return e;
  }
  function contentEl(){
    var sel = ['.blog-item-content .sqs-layout', '.blog-item-content',
               'article .sqs-layout', 'main .sqs-layout', 'main article', 'main'];
    for (var i=0;i<sel.length;i++){ var n=document.querySelector(sel[i]); if(n) return n; }
    return null;
  }

  // --- Auto header image ------------------------------------------------
  // The Squarespace blog template does not render a post's featured image on
  // the article page (it only feeds the social/OG image and the blog-grid
  // thumbnail). This pulls that same featured image in as an in-article header,
  // sourced from the per-article og:image meta (already sized ?format=1500w).
  // Runs on every /library/ article page, is idempotent, and does not depend on
  // the ARTICLES manifest so it also covers future posts automatically.
  function autoHeader(){
    if (location.pathname.indexOf(CFG.blogBase) !== 0) return;   // /library/<slug> only
    if (location.pathname.indexOf('/category/') > -1) return;     // not category listings
    var content = document.querySelector('.blog-item-content');
    if (!content || content.querySelector('.eob-auto-header')) return;  // absent or already added
    var meta = document.querySelector('meta[property="og:image"]') ||
               document.querySelector('meta[name="twitter:image"]');
    var src = meta && (meta.getAttribute('content') || '');
    if (!src) return;
    src = src.replace(/^http:\/\//, 'https://');
    if (src.indexOf('format=') === -1) src += (src.indexOf('?') > -1 ? '&' : '?') + 'format=1500w';
    var fig = el('figure', 'margin:0 0 30px;line-height:0;');
    fig.className = 'eob-auto-header';
    var img = el('img', 'display:block;width:100%;height:auto;border:1px solid ' + CFG.brand.rule + ';border-radius:3px;');
    img.src = src; img.alt = ''; img.setAttribute('loading', 'eager');
    fig.appendChild(img);
    content.insertBefore(fig, content.firstChild);
  }

  // --- Branded in-article graphics --------------------------------------
  // GRAPHICS: flat manifest. Each { slug, after, type, data }.
  //   after = heading-text substring to anchor after (graphic is SKIPPED if the
  //           heading is not found, so it never lands in the wrong place).
  //   type  = 'note' | 'stat' | 'table' | 'steps' | 'checklist'.
  // Populate from the article's own fact-checked text. Empty = module no-ops.
  var GFX = {
    accent:'#7A2129', accent2:'#1C2C3A', ink:'#1B1712', bg:'#F3F0E9',
    surface:'#ffffff', rule:'#DED7C7', muted:'#5A5348',
    head:'"Spectral",Georgia,serif', body:'"Public Sans",system-ui,sans-serif'
  };
  var GRAPHICS = [
    {
      "slug": "chief-of-staff-salary-guide",
      "after": "What the role pays in 2025",
      "type": "stat",
      "data": {
        "kicker": "US Chief of Staff pay, 2025",
        "items": [
          {
            "value": "$117.5k to $200k",
            "label": "span of observed company-stage medians"
          },
          {
            "value": "$160,000",
            "label": "overall median base, CoS Network 2025"
          },
          {
            "value": "$167,954",
            "label": "overall mean base, CoS Network 2025"
          },
          {
            "value": "56% / 54%",
            "label": "bonus / equity incidence in a small mixed-geography survey"
          }
        ]
      }
    },
    {
      "slug": "chief-of-staff-salary-guide",
      "after": "1. Company stage",
      "type": "table",
      "data": {
        "title": "Median base salary by company stage",
        "headers": [
          "Company stage",
          "Median base"
        ],
        "rows": [
          [
            "Bootstrapped",
            "$117,500"
          ],
          [
            "Seed",
            "$140,000"
          ],
          [
            "Series A",
            "$160,000"
          ],
          [
            "Series B",
            "$170,000"
          ],
          [
            "Series C",
            "$196,000"
          ],
          [
            "Series D",
            "$197,500"
          ],
          [
            "Late-stage private",
            "$190,000"
          ],
          [
            "Public company",
            "$200,000"
          ]
        ],
        "caption": "Ask a Chief of Staff, 2025 compensation report (n=512 overall; stage-cell sizes not published)."
      }
    },
    {
      "slug": "chief-of-staff-vs-executive-assistant-vs-coo",
      "after": "The quick version",
      "type": "table",
      "data": {
        "title": "Who owns what",
        "headers": [
          "Role",
          "What they own"
        ],
        "rows": [
          [
            "Executive assistant",
            "The leader's time and logistics"
          ],
          [
            "Chief of staff",
            "The leader's priorities and leadership rhythm"
          ],
          [
            "COO",
            "The company's operations, with formal authority"
          ]
        ],
        "caption": "The EA manages the day, the chief of staff manages the agenda, the COO manages the machine."
      }
    },
    {
      "slug": "three-types-of-chief-of-staff",
      "after": "Why the role splits into types",
      "type": "table",
      "data": {
        "title": "The three types of chief of staff",
        "headers": [
          "Type",
          "What they do",
          "A company needs one when"
        ],
        "rows": [
          [
            "Operator",
            "Turns strategy into execution",
            "Execution is the bottleneck"
          ],
          [
            "Strategist",
            "Combines operating skill with big-picture thinking",
            "Facing a strategic inflection"
          ],
          [
            "Proxy",
            "The leader's trusted stand-in",
            "The leader is the single point of failure"
          ]
        ]
      }
    },
    {
      "slug": "three-types-of-chief-of-staff",
      "after": "How to pick the right type",
      "type": "steps",
      "data": {
        "title": "Picking the type by working backward from the gap",
        "items": [
          {
            "h": "Name the bottleneck",
            "d": "Is it execution, strategy, or the leader's own bandwidth?"
          },
          {
            "h": "Match seniority to the type",
            "d": "A proxy needs the experience to be credible speaking for the leader; an operator can be earlier in their career."
          },
          {
            "h": "Write the job around the type",
            "d": "Describe the actual work and the outcomes you expect, not a vague title."
          },
          {
            "h": "Expect the type to evolve",
            "d": "Many start as operators and grow into strategist or proxy work as trust builds."
          }
        ]
      }
    },
    {
      "slug": "first-90-days-chief-of-staff-operating-plan",
      "after": "A 90-Day Plan on One Page",
      "type": "steps",
      "data": {
        "title": "The first 90 days at a glance",
        "items": [
          {
            "h": "Days 1 to 30: Diagnose",
            "d": "Listen widely, understand the principal, and map the operating rhythm. Change little."
          },
          {
            "h": "Days 31 to 60: Earn trust",
            "d": "Deliver one or two visible wins and build the working relationship across the leadership team."
          },
          {
            "h": "Days 61 to 90: Install the system",
            "d": "Set the operating cadence, stand up a single source of truth, and agree on how your success will be measured."
          }
        ]
      }
    },
    {
      "slug": "the-trust-equation",
      "after": "The Trust Equation",
      "type": "note",
      "data": {
        "title": "The Trust Equation",
        "body": "Trust = (Credibility + Reliability + Intimacy) / Self-Orientation. Three factors in the numerator build trust. The denominator, self-orientation, quietly erodes it. From The Trusted Advisor by Maister, Green, and Galford.",
        "variant": "info"
      }
    },
    {
      "slug": "the-trust-equation",
      "after": "Reading the equation as an operator",
      "type": "table",
      "data": {
        "title": "The four factors",
        "headers": [
          "Factor",
          "What it is"
        ],
        "rows": [
          [
            "Credibility",
            "About words. Can you be believed?"
          ],
          [
            "Reliability",
            "About actions. Do you do what you say you will do?"
          ],
          [
            "Intimacy",
            "About safety. Do people feel safe being open with you?"
          ],
          [
            "Self-orientation",
            "Where your focus sits: on yourself, or on the shared goal."
          ]
        ],
        "caption": "Intimacy and self-orientation move trust the most; credibility and reliability do the least on their own."
      }
    },
    {
      "slug": "prioritization-frameworks-for-operators",
      "after": "How to Actually Choose",
      "type": "table",
      "data": {
        "title": "Matching the framework to the decision",
        "headers": [
          "Framework",
          "Best for"
        ],
        "rows": [
          [
            "Eisenhower matrix",
            "Managing your own time and attention"
          ],
          [
            "RICE",
            "Defensible ranking of a backlog of comparable projects"
          ],
          [
            "ICE",
            "Fast, iterative experiment prioritization"
          ],
          [
            "MoSCoW",
            "Scoping what is in and out under a deadline"
          ],
          [
            "Value versus effort",
            "Quick group alignment on a whiteboard"
          ]
        ]
      }
    },
    {
      "slug": "prioritization-frameworks-for-operators",
      "after": "RICE: Scoring Ideas Against One Another",
      "type": "note",
      "data": {
        "title": "The RICE score",
        "body": "RICE score = (Reach times Impact times Confidence) divided by Effort. The confidence multiplier is the point: it explicitly discounts ideas built on shaky assumptions.",
        "variant": "info"
      }
    },
    {
      "slug": "negotiate-chief-of-staff-offer",
      "after": "The terms people forget",
      "type": "checklist",
      "data": {
        "title": "Movable terms beyond base salary",
        "items": [
          "Sign-on bonus, which can bridge a gap when base is capped",
          "Severance, which matters more in a role tied so closely to one person",
          "Title and level, which affect your next role as much as this one",
          "Refresh grants and review timing, so a strong first year is recognized",
          "Remote or relocation terms, and how comp is benchmarked if you work remotely"
        ]
      }
    },
    {
      "slug": "negotiate-chief-of-staff-offer",
      "after": "Mistakes that cost Chiefs of Staff money",
      "type": "checklist",
      "data": {
        "title": "Mistakes to avoid",
        "items": [
          "Accepting the title in place of scope",
          "Treating private equity as cash before you have ownership or fully diluted shares, strike price, the latest 409A and date, vesting, and the exercise window",
          "Ignoring severance in a principal-dependent role",
          "Negotiating past the point of goodwill"
        ]
      }
    },
    {
      "slug": "how-to-build-an-operating-cadence",
      "after": "A Practical Cadence to Start From",
      "type": "table",
      "data": {
        "title": "A workable default cadence",
        "headers": [
          "Layer",
          "Its job"
        ],
        "rows": [
          [
            "Daily standup",
            "Surface blockers fast so they get handled offline"
          ],
          [
            "Weekly tactical",
            "Review the key numbers and resolve cross-functional issues now"
          ],
          [
            "Monthly operating review",
            "Look at trends rather than snapshots"
          ],
          [
            "Quarterly planning",
            "Set priorities and review progress against goals"
          ],
          [
            "Annual strategy",
            "Set the year's direction and plan"
          ]
        ]
      }
    },
    {
      "slug": "how-to-build-an-operating-cadence",
      "after": "Design Principles That Keep a Cadence Healthy",
      "type": "checklist",
      "data": {
        "title": "Principles that keep a cadence healthy",
        "items": [
          "Protect the strategic layers from the tactical",
          "Keep the schedule stable so people can plan around it",
          "Make inputs flow between layers",
          "Move reporting out of live time and into pre-reads or dashboards",
          "Prune regularly; kill or merge meetings that no longer earn their place"
        ]
      }
    },
    {
      "slug": "equity-for-chiefs-of-staff",
      "after": "The three things you might be offered",
      "type": "table",
      "data": {
        "title": "Forms of startup equity",
        "headers": [
          "Form",
          "What it is"
        ],
        "rows": [
          [
            "ISOs",
            "Right to buy shares at a strike price; employee-only, with potentially favorable tax treatment"
          ],
          [
            "NSOs",
            "Right to buy at a strike price; can go to contractors, taxed as ordinary income at exercise"
          ],
          [
            "RSUs",
            "A promise of actual shares delivered at vesting; more common at later-stage and public companies"
          ]
        ]
      }
    },
    {
      "slug": "equity-for-chiefs-of-staff",
      "after": "The questions to ask before you sign",
      "type": "checklist",
      "data": {
        "title": "Ask before you accept",
        "items": [
          "How many total fully diluted shares are outstanding?",
          "What is the current strike price and the date of the last 409A valuation?",
          "What was the price and post-money valuation of the most recent round?",
          "What is the vesting schedule and cliff?",
          "ISOs, NSOs, or RSUs?",
          "What is the post-termination exercise window?",
          "How will dilution, refresh grants, and a change of control affect the grant?"
        ]
      }
    },
    {
      "slug": "what-does-a-chief-of-staff-do",
      "after": "The five functions at the core of the job",
      "type": "table",
      "data": {
        "title": "The five core functions",
        "headers": [
          "Function",
          "What it means"
        ],
        "rows": [
          [
            "Air traffic controller",
            "Manages the flow of decisions, meetings, and requests to the leader"
          ],
          [
            "Integrator",
            "Connects siloed work streams that no single executive owns"
          ],
          [
            "Communicator",
            "Links the leadership team to the rest of the organization"
          ],
          [
            "Honest broker",
            "Gives the leader a wide, unbiased read on an issue"
          ],
          [
            "Confidant",
            "Holds sensitive context and unfinished thinking discreetly"
          ]
        ],
        "caption": "Dan Ciampa, Harvard Business Review, 2020."
      }
    },
    {
      "slug": "what-does-a-chief-of-staff-do",
      "after": "How to tell a real chief of staff role from a title",
      "type": "checklist",
      "data": {
        "title": "Signals of a real role",
        "items": [
          "Direct access to the principal, not three layers down",
          "Ownership of priorities and outcomes, not just meeting logistics",
          "A seat in the room where the leadership team sets direction"
        ]
      }
    }
  ];

  function gfxShell(title, kicker){
    var w = el('figure','margin:2rem 0;padding:1.25rem 1.4rem;background:'+GFX.surface+';border:1px solid '+GFX.rule+';border-top:3px solid '+GFX.accent+';');
    if (kicker) w.appendChild(el('figcaption','font:700 .64rem/1 '+GFX.head+';letter-spacing:.14em;text-transform:uppercase;color:'+GFX.accent+';margin-bottom:.6rem;', kicker));
    if (title)  w.appendChild(el('div','font:600 1.12rem/1.3 '+GFX.head+';color:'+GFX.ink+';margin-bottom:.85rem;', title));
    return w;
  }
  function renderNote(g){
    var d=g.data||{}, warn=(d.variant==='warn');
    var box=el('aside','margin:2rem 0;padding:1.05rem 1.3rem;background:'+GFX.bg+';border-left:4px solid '+(warn?GFX.accent:GFX.accent2)+';');
    if(d.title) box.appendChild(el('div','font:700 .66rem/1 '+GFX.head+';letter-spacing:.12em;text-transform:uppercase;color:'+(warn?GFX.accent:GFX.accent2)+';margin-bottom:.4rem;', d.title));
    if(d.body)  box.appendChild(el('div','font:400 .96rem/1.55 '+GFX.body+';color:'+GFX.ink+';', d.body));
    return box;
  }
  function renderStat(g){
    var d=g.data||{}, w=gfxShell(d.title, d.kicker||'By the numbers');
    var row=el('div','display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:1rem;');
    (d.items||[]).forEach(function(it){
      var c=el('div');
      c.appendChild(el('div','font:700 1.7rem/1 '+GFX.head+';color:'+GFX.accent+';', it.value));
      c.appendChild(el('div','font:500 .82rem/1.35 '+GFX.body+';color:'+GFX.muted+';margin-top:.3rem;', it.label));
      row.appendChild(c);
    });
    w.appendChild(row); return w;
  }
  function renderTable(g){
    var d=g.data||{}, w=gfxShell(d.title, d.kicker||'At a glance');
    var scroll=el('div','overflow-x:auto;');
    var t=el('table','width:100%;border-collapse:collapse;font:400 .9rem/1.4 '+GFX.body+';color:'+GFX.ink+';');
    if(d.headers){ var thead=el('thead'), tr=el('tr');
      d.headers.forEach(function(h){ tr.appendChild(el('th','text-align:left;padding:.55rem .7rem;background:'+GFX.accent2+';color:#fff;font:600 .82rem '+GFX.body+';', h)); });
      thead.appendChild(tr); t.appendChild(thead); }
    var tb=el('tbody');
    (d.rows||[]).forEach(function(r,ri){ var tr=el('tr', ri%2?'background:'+GFX.bg+';':'');
      r.forEach(function(cell){ tr.appendChild(el('td','padding:.5rem .7rem;border-bottom:1px solid '+GFX.rule+';', cell)); });
      tb.appendChild(tr); });
    t.appendChild(tb); scroll.appendChild(t); w.appendChild(scroll);
    if(d.caption) w.appendChild(el('div','font:400 .78rem/1.4 '+GFX.body+';color:'+GFX.muted+';margin-top:.6rem;', d.caption));
    return w;
  }
  function renderSteps(g){
    var d=g.data||{}, w=gfxShell(d.title, d.kicker||'Step by step');
    var ol=el('div');
    (d.items||[]).forEach(function(it,i){
      var row=el('div','display:flex;gap:.85rem;padding:.6rem 0;'+(i?'border-top:1px solid '+GFX.rule+';':''));
      row.appendChild(el('div','flex:0 0 auto;width:1.7rem;height:1.7rem;border-radius:50%;background:'+GFX.accent2+';color:#fff;font:700 .9rem/1.7rem '+GFX.head+';text-align:center;', String(i+1)));
      var body=el('div');
      body.appendChild(el('div','font:600 .98rem/1.35 '+GFX.body+';color:'+GFX.ink+';', it.h));
      if(it.d) body.appendChild(el('div','font:400 .9rem/1.5 '+GFX.body+';color:'+GFX.muted+';margin-top:.15rem;', it.d));
      row.appendChild(body); ol.appendChild(row);
    });
    w.appendChild(ol); return w;
  }
  function renderChecklist(g){
    var d=g.data||{}, w=gfxShell(d.title, d.kicker||'Checklist');
    var ul=el('div');
    (d.items||[]).forEach(function(it){
      var row=el('div','display:flex;gap:.6rem;align-items:flex-start;padding:.35rem 0;');
      row.appendChild(el('div','flex:0 0 auto;color:'+GFX.accent+';font:700 1rem/1.4 '+GFX.body+';','✓'));
      row.appendChild(el('div','font:400 .95rem/1.5 '+GFX.body+';color:'+GFX.ink+';', it));
      ul.appendChild(row);
    });
    w.appendChild(ul); return w;
  }
  function renderGraphic(g){
    switch(g.type){
      case 'note': return renderNote(g);
      case 'stat': return renderStat(g);
      case 'table': return renderTable(g);
      case 'steps': return renderSteps(g);
      case 'checklist': return renderChecklist(g);
    }
    return null;
  }
  function graphics(slug, host){
    var mine = GRAPHICS.filter(function(x){ return x.slug===slug; });
    if(!mine.length) return;
    var heads = host.querySelectorAll('h2, h3');
    mine.forEach(function(g, idx){
      var id='eob-gfx-'+idx; if(byId(id)) return;
      var node; try{ node=renderGraphic(g); }catch(e){ node=null; }
      if(!node) return; node.id=id;
      var want=(g.after||'').toLowerCase(), anchor=null, i;
      if(want){ for(i=0;i<heads.length;i++){ if((heads[i].textContent||'').toLowerCase().indexOf(want)!==-1){ anchor=heads[i]; break; } } if(!anchor) return; }
      if(anchor){ anchor.parentNode.insertBefore(node, anchor.nextSibling); }
      else { host.appendChild(node); }
    });
  }

  // ---- 1. Keep Reading ---------------------------------------------------
  function keepReading(slug, host){
    if (byId('eob-keep-reading')) return;
    var me = findArticle(slug), i;
    if (!me) return;
    var base = currentBase();
    var same = ARTICLES.filter(function(a){ return a.s!==slug && a.p===me.p; });
    var other = ARTICLES.filter(function(a){ return a.s!==slug && a.p!==me.p; });
    // stable rotation so different articles surface different neighbours
    var seed = slug.length;
    function rot(arr){ return arr.slice(seed % (arr.length||1)).concat(arr.slice(0, seed % (arr.length||1))); }
    var picks = rot(same).concat(rot(other)).slice(0, CFG.maxRelated);
    if (!picks.length) return;

    var b = CFG.brand;
    var wrap = el('section', 'margin:3.5rem 0 1rem;padding-top:2rem;border-top:2px solid '+b.ink+';');
    wrap.id = 'eob-keep-reading';
    wrap.appendChild(el('div',
      'font:600 .72rem/1 "Public Sans",system-ui,sans-serif;letter-spacing:.16em;text-transform:uppercase;color:'+b.oxblood+';margin-bottom:1rem;',
      'Keep Reading'));
    var grid = el('div','display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;');
    picks.forEach(function(a){
      var card = el('a', 'display:block;padding:1rem 1.1rem;background:'+b.paper+';border:1px solid '+b.rule+';border-left:3px solid '+b.oxblood+';text-decoration:none;color:'+b.ink+';transition:border-color .15s;');
      card.href = base + a.s;
      card.onmouseover = function(){ card.style.borderLeftColor = b.navy; };
      card.onmouseout  = function(){ card.style.borderLeftColor = b.oxblood; };
      card.appendChild(el('div','font:600 .64rem/1 "Public Sans",system-ui,sans-serif;letter-spacing:.12em;text-transform:uppercase;color:'+b.slate+';margin-bottom:.4rem;', a.p));
      card.appendChild(el('div','font:600 1.02rem/1.3 "Spectral",Georgia,serif;color:'+b.ink+';', a.t));
      grid.appendChild(card);
    });
    wrap.appendChild(grid);
    host.appendChild(wrap);
  }

  // ---- 2. FAQ polish -----------------------------------------------------
  function faqPolish(host){
    var heads = host.querySelectorAll('h2, h3');
    var b = CFG.brand, inFaq = false;
    for (var i=0;i<heads.length;i++){
      var h = heads[i], txt = (h.textContent||'').trim().toLowerCase();
      if (h.tagName==='H2'){ inFaq = /frequently asked|faq|common questions/.test(txt); continue; }
      if (inFaq && h.tagName==='H3' && !h.getAttribute('data-eob-faq')){
        h.setAttribute('data-eob-faq','1');
        h.style.color = b.navy;
        h.style.marginTop = '1.6rem';
      }
    }
  }

  // ---- 3. Callouts -------------------------------------------------------
  function callout(slug, host){
    if (!CALLOUTS.length || byId('eob-callout')) return;
    var me = findArticle(slug), i;
    var hay = (slug + ' ' + (me?me.t:'')).toLowerCase();
    var hit = null;
    for (i=0;i<CALLOUTS.length;i++){
      var c = CALLOUTS[i];
      if (!c.href || c.href.indexOf('REPLACE_WITH')!==-1) continue; // dormant until real URL
      var m = c.match || [];
      for (var j=0;j<m.length;j++){ if (hay.indexOf(String(m[j]).toLowerCase())!==-1){ hit=c; break; } }
      if (hit) break;
    }
    if (!hit) return;
    var b = CFG.brand;
    var box = el('aside','margin:2.25rem 0;padding:1.25rem 1.4rem;background:#fff;border:1px solid '+b.rule+';border-top:3px solid '+b.oxblood+';');
    box.id = 'eob-callout';
    box.appendChild(el('div','font:600 .66rem/1 "Public Sans",system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:'+b.oxblood+';margin-bottom:.5rem;','Recommended'));
    if (hit.title) box.appendChild(el('div','font:600 1.1rem/1.3 "Spectral",Georgia,serif;color:'+b.ink+';margin-bottom:.4rem;', hit.title));
    if (hit.body)  box.appendChild(el('div','font:400 .95rem/1.5 "Public Sans",system-ui,sans-serif;color:'+b.slate+';margin-bottom:.8rem;', hit.body));
    if (hit.cta && hit.href){
      var a = el('a','display:inline-block;padding:.55rem 1.1rem;background:'+b.navy+';color:#fff;text-decoration:none;font:600 .9rem "Public Sans",system-ui,sans-serif;', hit.cta);
      a.href = hit.href;
      if (hit.href.charAt(0) === '/'){ a.rel = 'noopener'; }               // internal (site) link
      else { a.rel = 'sponsored noopener'; a.target = '_blank'; }          // affiliate / external
      box.appendChild(a);
    }
    // insert after the second H2 in the content, else at ~40% down
    var h2s = host.querySelectorAll('h2');
    if (h2s.length >= 2){ h2s[1].parentNode.insertBefore(box, h2s[1].nextSibling); }
    else { host.appendChild(box); }
  }

  // ---- 3b. Tool callouts ---------------------------------------------------
  // A SECOND, independent callout slot that routes readers into the four free
  // interactive tools. Deliberately separate from module 3 so a tool callout and
  // a product/affiliate callout can coexist on the same article: module 3 injects
  // after the 2nd H2, this one injects at a LATE heading (5th H2 where available)
  // and refuses to sit adjacent to the module-3 box. Idempotent via #eob-tool-callout.
  function isFaqHeading(h){
    return /frequently asked|faq|common questions/i.test((h.textContent || '').trim());
  }
  function toolCallout(slug, host){
    if (!TOOL_CALLOUTS.length || byId('eob-tool-callout')) return;
    var hit = null, i, j;
    for (i=0;i<TOOL_CALLOUTS.length && !hit;i++){
      var m = TOOL_CALLOUTS[i].match || [];
      for (j=0;j<m.length;j++){ if (slug === m[j]){ hit = TOOL_CALLOUTS[i]; break; } }
    }
    if (!hit || !hit.href) return;

    var b = CFG.brand;
    var box = el('aside','margin:2.25rem 0;padding:1.25rem 1.4rem;background:'+b.paper+';border:1px solid '+b.rule+';border-left:4px solid '+b.navy+';');
    box.id = 'eob-tool-callout';
    box.appendChild(el('div','font:600 .66rem/1 "Public Sans",system-ui,sans-serif;letter-spacing:.14em;text-transform:uppercase;color:'+b.navy+';margin-bottom:.5rem;','Free tool'));
    if (hit.title) box.appendChild(el('div','font:600 1.1rem/1.3 "Spectral",Georgia,serif;color:'+b.ink+';margin-bottom:.4rem;', hit.title));
    if (hit.body)  box.appendChild(el('div','font:400 .95rem/1.5 "Public Sans",system-ui,sans-serif;color:'+b.slate+';margin-bottom:.8rem;', hit.body));
    if (hit.cta){
      var a = el('a','display:inline-block;padding:.55rem 1.1rem;background:'+b.oxblood+';color:#fff;text-decoration:none;font:600 .9rem "Public Sans",system-ui,sans-serif;border-radius:2px;', hit.cta);
      a.href = hit.href;                 // always an internal tool page
      a.rel = 'noopener';
      box.appendChild(a);
    }

    // Anchor: a late H2. Candidates are tried in preference order (5th H2 first)
    // and a heading is rejected if it is the FAQ heading, if the module-3 box is
    // already sitting on it (never stack the two), or if a branded graphic is
    // already anchored under it (graphics() runs first, so we would land on top
    // of a figure with no prose between them). Falls back to appending at the end
    // of the body, which still lands above Keep Reading because that module runs
    // after this one.
    var h2s = host.querySelectorAll('h2');
    var order = [4, 5, 3, 6, 2];
    for (i=0;i<order.length;i++){
      var anchor = h2s[order[i]];
      if (!anchor || isFaqHeading(anchor)) continue;
      var prev = anchor.previousElementSibling;
      if (prev && prev.id === 'eob-callout') continue;              // module-3 box owns this heading
      var next = anchor.nextElementSibling;
      if (next && /^eob-gfx-/.test(next.id || '')) continue;        // a graphic owns this heading
      anchor.parentNode.insertBefore(box, anchor.nextSibling);
      return;
    }
    host.appendChild(box);
  }

  // ---- 4. Shop polish ------------------------------------------------------
  // Styles the NATIVE Squarespace store (list + product detail pages) to
  // Design System v2. Gated on the products collection body class, idempotent,
  // and fully reversible (remove this module and the shop reverts to native).
  function shopPolish(){
    if (!document.body.classList.contains('collection-type-products')) return;
    var b = CFG.brand, oxDeep = '#5E181F', inkSoft = '#3A342B';

    // 4a. Collapse empty leftover layout-engine sections (deleting a code
    // block leaves a blank section shell with a huge min-height above the grid).
    var secs = document.querySelectorAll('.page-section.layout-engine-section');
    for (var i=0;i<secs.length;i++){
      var s = secs[i];
      if (!s.querySelector('.sqs-block') && !(s.innerText||'').trim()) s.style.display = 'none';
    }

    // 4b. Design-system CSS for the native store components.
    if (!byId('eob-shop-style')){
      var css = ''
      // list page: cards
      + '.product-list-section{background:'+b.paper+';}'
      + '.product-list-header{display:none!important;}' // mobile "Shop" title collides with the site header; the masthead replaces it
      + '.product-list-item-link{text-decoration:none!important;border-bottom:none!important;}'
      + '.product-list-image-wrapper{border:1px solid '+b.rule+';background:#fff;}'
      + '.product-list-item-meta{padding-top:1rem;}'
      + '.product-list-item-title{font:600 1.3rem/1.25 "Spectral",Georgia,serif!important;color:'+b.ink+'!important;text-decoration:none!important;}'
      + '.product-list-item-link:hover .product-list-item-title{color:'+b.oxblood+'!important;}'
      + '.product-list-item-price{font:500 .85rem/1 "IBM Plex Mono",Consolas,monospace!important;color:'+b.slate+'!important;letter-spacing:.06em;margin-top:.4rem;}'
      + '.product-list-item-title *,.product-list-item-price *{text-decoration:none!important;}'
      // detail page: type
      + '.product-title{font:600 2.35rem/1.15 "Spectral",Georgia,serif!important;color:'+b.ink+'!important;}'
      + '.product-price{font:500 1.1rem/1 "IBM Plex Mono",Consolas,monospace!important;color:'+b.oxblood+'!important;letter-spacing:.05em;margin:.5rem 0 .75rem;}'
      + '.product-description p{font:400 1rem/1.6 "Public Sans",system-ui,sans-serif!important;color:'+inkSoft+'!important;}'
      + '.product-nav-breadcrumb-link{font:500 .72rem/1 "IBM Plex Mono",Consolas,monospace!important;letter-spacing:.14em;text-transform:uppercase;color:'+b.slate+'!important;text-decoration:none!important;}'
      + '.product-nav-breadcrumb-link:hover{color:'+b.oxblood+'!important;}'
      // detail page: add-to-cart button (v2: oxblood fill, 2px radius)
      + '.sqs-add-to-cart-button{background:'+b.oxblood+'!important;border-radius:2px!important;border:none!important;}'
      + '.sqs-add-to-cart-button:hover{background:'+oxDeep+'!important;}'
      + '.sqs-add-to-cart-button .sqs-add-to-cart-button-inner{font-family:"Public Sans",system-ui,sans-serif!important;font-weight:600!important;color:'+b.paper+'!important;}'
      // detail page: gallery shows the full square card, no cropping
      + '.product-gallery-slides-item img{object-fit:contain!important;background:'+b.paper+'!important;}'
      + '.product-gallery-thumbnails img{border:1px solid '+b.rule+';}'
      // masthead
      + '#eob-shop-masthead{border-top:2px solid '+b.ink+';padding:1.3rem 0 0;margin:6.5rem 0 2.4rem;}'
      + '#eob-shop-masthead .eob-sm-row{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:.5rem;}'
      + '#eob-shop-masthead .eob-sm-name{font:600 1.15rem/1 "Spectral",Georgia,serif;color:'+b.ink+';}'
      + '#eob-shop-masthead .eob-sm-name span{color:'+b.oxblood+';}'
      + '#eob-shop-masthead .eob-sm-date{font:500 .7rem/1 "IBM Plex Mono",Consolas,monospace;letter-spacing:.16em;text-transform:uppercase;color:'+b.slate+';}'
      + '#eob-shop-masthead h1{font:600 clamp(1.9rem,4.5vw,2.7rem)/1.12 "Spectral",Georgia,serif;color:'+b.ink+';margin:1.6rem 0 .9rem;}'
      + '#eob-shop-masthead p{font:400 1.02rem/1.6 "Public Sans",system-ui,sans-serif;color:'+b.slate+';max-width:640px;margin:0;}';
      var st = document.createElement('style');
      st.id = 'eob-shop-style';
      st.textContent = css;
      document.head.appendChild(st);
    }

    // 4c. Briefing-document masthead above the product grid (list page only).
    var list = document.querySelector('.product-list-section .product-list');
    if (list && !byId('eob-shop-masthead')){
      var m = document.createElement('header');
      m.id = 'eob-shop-masthead';
      m.innerHTML = ''
        + '<div class="eob-sm-row">'
        +   '<div class="eob-sm-name">The Exec Ops Brief<span>.</span></div>'
        +   '<div class="eob-sm-date">The Shop / Paid Products</div>'
        + '</div>'
        + '<h1>The free library, gone deeper.</h1>'
        + '<p>A small shelf of evergreen templates and guides that pick up where the free downloads leave off. The same systems the best operators run, packaged in full so you can put them to work the same day. No subscriptions. Buy the file, keep it, use it.</p>';
      list.insertBefore(m, list.firstChild);
    }
  }

  // ---- 5. Link repair ------------------------------------------------------
  // Two page slugs changed after the sources were written; pasted pages and
  // the footer still carry the old hrefs. Rewrite them site-wide until every
  // pasted page is refreshed from the corrected pages_html sources.
  var LINK_FIXES = {
    '/first-90-days-tool': '/first-90-days',
    '/guide-become-chief-of-staff': '/how-to-become-a-chief-of-staff',
    '/library/first-90-days-operating-plan': '/library/first-90-days-chief-of-staff-operating-plan'
  };
  function fixLinks(){
    Object.keys(LINK_FIXES).forEach(function(bad){
      document.querySelectorAll('a[href="' + bad + '"]').forEach(function(a){
        a.setAttribute('href', LINK_FIXES[bad]);
      });
    });
  }

  // ---- 6. Home polish ------------------------------------------------------
  // The pasted home page carries a static role count/cadence and two mobile
  // overflow bugs. Self-heal here until the page is re-pasted from the
  // corrected pages_html/home.html source.
  function homePolish(){
    var home = document.getElementById('eob-home');
    if (!home) return;
    var st = document.createElement('style');
    st.textContent = '@media(max-width:480px){' +
      '#eob-home .sub-form{flex-wrap:wrap}' +
      '#eob-home .sub-form .btn{flex:1 1 100%}' +
      '#eob-home .dossier .d-row{flex-wrap:wrap}' +
      '}';
    document.head.appendChild(st);
    home.querySelectorAll('.mono').forEach(function(el){
      if (/updated weekly/i.test(el.textContent) && !el.children.length){
        el.textContent = el.textContent.replace(/updated weekly/i, 'updated daily');
      }
    });
    if (!window.fetch) return;
    fetch('https://gaughanadrienne-gif.github.io/execops-brief-assets/jobboard/roles.json')
      .then(function(r){ return r.json(); })
      .then(function(data){
        var roles = (data && data.roles) || [];
        if (!roles.length) return;
        var n = roles.length;
        var firms = {};
        roles.forEach(function(r){ if (r.source) firms[r.source] = 1; });
        var nf = Object.keys(firms).length;
        home.querySelectorAll('.dossier .d-row').forEach(function(row){
          var lab = row.firstElementChild ? row.firstElementChild.textContent : '';
          var v = row.querySelector('.v');
          if (!v) return;
          if (/live roles/i.test(lab)) v.textContent = String(n);
          if (/sourced from/i.test(lab) && nf) v.textContent = nf + ' search firms';
        });
        home.querySelectorAll('.mono').forEach(function(el){
          if (/\d+ roles live now/i.test(el.textContent) && !el.children.length){
            el.textContent = el.textContent.replace(/\d+ roles live now/i, n + ' roles live now');
          }
        });
      })
      .catch(function(){});
  }

  // ---- 7. Form feedback self-heal -----------------------------------------
  // The pasted pages carry their own .eob-ml-form binding script, but a paste
  // or copy edit can break it (2026-07-08: an unescaped apostrophe in the
  // success string killed the whole IIFE on /resources and no form gave any
  // feedback). This module binds any form the page script missed. Idempotent:
  // it respects the same data-eobBound flag the page scripts set.
  function formFeedback(){
    var forms = document.querySelectorAll('.eob-ml-form');
    if (!forms.length) return;
    if (!document.querySelector('iframe[name="eob-ml-frame"]')){
      var frame = document.createElement('iframe');
      frame.name = 'eob-ml-frame';
      frame.style.display = 'none';
      frame.setAttribute('aria-hidden', 'true');
      document.body.appendChild(frame);
    }
    forms.forEach(function(form){
      if (form.dataset.eobBound === '1') return;
      form.dataset.eobBound = '1';
      form.setAttribute('target', 'eob-ml-frame');
      form.addEventListener('submit', function(){
        var button = form.querySelector('button[type="submit"]');
        if (button){ button.disabled = true; button.textContent = 'Sending...'; }
        window.setTimeout(function(){
          form.innerHTML = '<div class="eob-form-success" role="status">You\'re in. Check your inbox for the next note.</div>';
        }, 900);
      });
    });
  }

  // ---- 8. Subscriber memory ------------------------------------------------
  // Free tools never re-gate a known subscriber. Contract shared with the
  // /resources picker page script (do not rename):
  //   localStorage eob_sub_email = subscriber email (plain string)
  //   localStorage eob_sub_tools = JSON array of MailerLite form ids requested
  // An email is learned from (a) a ?e=<email> param carried by links in our
  // own emails ({$email} personalization) or (b) any .eob-ml-form submit.
  var LS_EMAIL = "eob_sub_email", LS_TOOLS = "eob_sub_tools";
  var BRIEF_FORM_ID = "192281502704207669";
  var EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  function lsGet(k){ try { return window.localStorage.getItem(k); } catch(e){ return null; } }
  function lsSet(k, v){ try { window.localStorage.setItem(k, v); } catch(e){} }
  function subEmail(){ var v = lsGet(LS_EMAIL); return (v && EMAIL_RE.test(v)) ? v : ""; }
  function rememberSub(email, formId){
    if (email && EMAIL_RE.test(email)) lsSet(LS_EMAIL, email.trim());
    if (formId && formId !== BRIEF_FORM_ID){
      var t;
      try { t = JSON.parse(lsGet(LS_TOOLS) || "[]"); } catch(e){ t = []; }
      if (!Array.isArray(t)) t = [];
      if (t.indexOf(formId) === -1){ t.push(formId); lsSet(LS_TOOLS, JSON.stringify(t)); }
    }
  }
  function subMemory(){
    // (a) email-link handoff: any page ?e=you@work.com -> store, strip from URL
    try {
      var m = /[?&]e=([^&]+)/.exec(window.location.search);
      if (m){
        var em = "";
        try { em = decodeURIComponent(m[1]); } catch(e){}
        if (EMAIL_RE.test(em)) rememberSub(em, "");
        var clean = window.location.search.replace(/[?&]e=[^&]+/, "").replace(/^&/, "?");
        window.history.replaceState(null, "", window.location.pathname + (clean.length > 1 ? clean : "") + window.location.hash);
      }
    } catch(e){}
    // (b) learn from any opt-in submit (capture phase; UI stays with the page
    // scripts / module 7, works regardless of who bound the form)
    document.addEventListener("submit", function(ev){
      var f = ev.target;
      if (!f || !f.classList || !f.classList.contains("eob-ml-form")) return;
      var inp = f.querySelector('input[type="email"]');
      var idm = /\/forms\/(\d+)\/subscribe/.exec(f.getAttribute("action") || "");
      if (inp && inp.value) rememberSub(inp.value.trim(), idm ? idm[1] : "");
    }, true);
    // (c) known-subscriber transform for opt-in forms site-wide. The
    // /resources picker page owns its own UI (its bar id marks the new markup).
    var email = subEmail();
    if (!email || byId("eob-pick-bar")) return;
    document.querySelectorAll(".eob-ml-form").forEach(function(form){
      if (form.dataset.eobKnown === "1") return;
      var inp = form.querySelector('input[type="email"]');
      var btn = form.querySelector('button[type="submit"]');
      if (!inp || !btn) return;
      form.dataset.eobKnown = "1";
      var idm = /\/forms\/(\d+)\/subscribe/.exec(form.getAttribute("action") || "");
      if (idm && idm[1] === BRIEF_FORM_ID){
        form.innerHTML = '<div class="eob-form-success" role="status">' + "You're on the list." + "</div>";
        return;
      }
      inp.value = email;
      inp.hidden = true;
      btn.dataset.eobOrig = btn.textContent;
      btn.textContent = "Send to my inbox";
      var esc = document.createElement("button");
      esc.type = "button";
      esc.textContent = "Not you? Use a different email";
      esc.style.cssText = "background:none;border:none;cursor:pointer;font:400 .7rem 'IBM Plex Mono',monospace;color:#6B6255;text-decoration:underline;padding:.2rem 0;";
      esc.addEventListener("click", function(){
        try { window.localStorage.removeItem(LS_EMAIL); } catch(e){}
        inp.value = "";
        inp.hidden = false;
        btn.textContent = btn.dataset.eobOrig || "Get the download";
        if (esc.parentNode) esc.parentNode.removeChild(esc);
        form.dataset.eobKnown = "";
      });
      form.appendChild(esc);
    });
  }

  // ---- 9. Picker bar reparent fix -------------------------------------------
  // Squarespace's .fe-block wrapper carries an identity transform, which turns
  // the send bar's position:fixed into "fixed to the block" (it rendered at the
  // bottom of the page, invisible). Move the bar to <body> and carry its CSS
  // unscoped with literal colors so it works from there. Idempotent: no-ops on
  // pages without the bar, and a future paste that already reparents is fine.
  function pickBarFix(){
    var bar = byId("eob-pick-bar");
    if (!bar) return;
    if (bar.parentNode !== document.body) document.body.appendChild(bar);
    if (!byId("eob-pick-bar-css")){
      var st = document.createElement("style");
      st.id = "eob-pick-bar-css";
      st.textContent =
        '#eob-pick-bar{position:fixed;left:0;right:0;bottom:0;z-index:99999;background:#1C2C3A;border-top:3px solid #7A2129;transform:translateY(110%);transition:transform .25s ease;padding:.75rem 0;font-family:"Public Sans",system-ui,sans-serif}' +
        '#eob-pick-bar *{box-sizing:border-box;margin:0;padding:0}' +
        '#eob-pick-bar [hidden]{display:none !important}' +
        '#eob-pick-bar.on{transform:none}' +
        '#eob-pick-bar .bar-wrap{max-width:1080px;margin:0 auto;padding:0 28px;display:flex;align-items:center;gap:1rem;flex-wrap:wrap}' +
        '#eob-pick-bar .count{font-family:"IBM Plex Mono",monospace;font-size:.72rem;letter-spacing:.1em;text-transform:uppercase;color:#A9B2BD}' +
        '#eob-pick-bar .note{font-family:"IBM Plex Mono",monospace;font-size:.72rem;color:#d9a7a2}' +
        '#eob-pick-bar form{display:flex;gap:.5rem;flex:1;min-width:16rem;max-width:26rem;margin-left:auto}' +
        '#eob-pick-bar input{flex:1;min-width:0;border:1px solid #33465a;border-radius:2px;padding:.62rem .9rem;font-family:"Public Sans",system-ui,sans-serif;font-size:.92rem;color:#fff;background:#16232f}' +
        '#eob-pick-bar input::placeholder{color:#7f8b98}' +
        '#eob-pick-bar input:focus{outline:none;border-color:#7A2129}' +
        '#eob-pick-bar button[type="submit"]{display:inline-flex;align-items:center;justify-content:center;font-family:"Public Sans",system-ui,sans-serif;font-weight:600;font-size:.88rem;border-radius:2px;cursor:pointer;border:1px solid transparent;padding:.62rem 1.1rem;background:#7A2129;color:#fff;white-space:nowrap;transition:background .16s}' +
        '#eob-pick-bar button[type="submit"]:hover{background:#5E181F}' +
        '#eob-pick-bar #eob-pick-notyou{background:none;border:none;cursor:pointer;font-family:"IBM Plex Mono",monospace;font-size:.7rem;color:#7f8b98;text-decoration:underline;padding:0}' +
        '@media(max-width:560px){#eob-pick-bar .bar-wrap{gap:.6rem}#eob-pick-bar form{min-width:100%;margin-left:0}}';
      document.head.appendChild(st);
    }
  }

  // ---- boot --------------------------------------------------------------
  function run(){
    var slug = currentSlug();
    try { fixLinks(); } catch(e){}             // stale slug rewrite (site-wide)
    try { formFeedback(); } catch(e){}         // opt-in form success feedback backstop (site-wide)
    try { subMemory(); } catch(e){}            // subscriber memory: ?e= handoff + known-sub one-click (site-wide)
    try { pickBarFix(); } catch(e){}           // /resources send bar: escape the transformed fe-block wrapper
    try { homePolish(); } catch(e){}           // home page mobile overflow + live counts
    try { autoHeader(); } catch(e){}           // featured image -> in-article header (any article page)
    try { shopPolish(); } catch(e){}           // native store styling (shop list + product pages)
    if (!slug || !findArticle(slug)) return;   // only on known article pages (path-agnostic)
    var host = contentEl();
    if (!host) return;
    try { graphics(slug, host); } catch(e){}
    try { callout(slug, host); } catch(e){}
    try { toolCallout(slug, host); } catch(e){}   // separate slot: free-tool routing
    try { faqPolish(host); } catch(e){}
    try { keepReading(slug, host); } catch(e){}
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', run);
  else run();
})();
