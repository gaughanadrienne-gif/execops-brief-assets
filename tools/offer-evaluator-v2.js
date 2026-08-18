(function(){
  "use strict";
  var root = document.getElementById("eob-offer");
  if (!root) return;

  var data = null;
  var ROLE_LABEL = {
    cos:"Chief of Staff",
    ea:"Executive Assistant",
    senior_ea:"Senior Executive Assistant",
    ops:"Executive Operations / BizOps"
  };
  var STATUS_CLASS = {
    strong:"eob-g-strong",
    solid:"eob-g-solid",
    below:"eob-g-below",
    wait:"eob-g-wait"
  };
  var TERMS = [
    { id:"eob-oe-t-severance", name:"Severance", why:"what applies if the principal leaves, the role changes, or employment ends." },
    { id:"eob-oe-t-vesting", name:"Vesting schedule and cliff", why:"when the grant vests and what happens during year one.", equityOnly:true },
    { id:"eob-oe-t-review", name:"Refresh grants and review timing", why:"when compensation is reviewed and whether refresh grants are available." },
    { id:"eob-oe-t-title", name:"Title and level clarity", why:"the internal level affects future roles as much as the external title." },
    { id:"eob-oe-t-window", name:"Post-termination exercise window", why:"how long vested private options can be exercised after leaving.", optionsOnly:true },
    { id:"eob-oe-t-change", name:"Change-of-control treatment", why:"what happens to the role, severance, and unvested compensation in a transaction." },
    { id:"eob-oe-t-benefits", name:"Benefits and flexibility", why:"health, retirement, PTO, work mode, and agreed flexibility are documented." }
  ];

  function $(id){ return root.querySelector("#" + id); }
  function money(n){ return "$" + Math.round(n).toLocaleString("en-US"); }
  /* Share -> percentage string, straight from compensation-data.json. Survey
     percentages are never retyped into the copy; they are read and formatted
     here, so a dataset update changes every sentence that quotes it. */
  function pct(v){ return (Math.round(v * 1000) / 10) + "%"; }
  /* Months between a YYYY-MM valuation date and today. Null when unparsable. */
  function monthsSince(ym){
    var m = /^(\d{4})-(\d{1,2})$/.exec(String(ym || "").trim());
    if (!m) return null;
    var y = parseInt(m[1], 10), mo = parseInt(m[2], 10);
    if (!(mo >= 1 && mo <= 12)) return null;
    var now = new Date();
    return (now.getFullYear() - y) * 12 + (now.getMonth() + 1 - mo);
  }
  /* The minus sign is preserved deliberately. Stripping it used to turn -10
     into 10 and evaluate an offer the user never typed. */
  function parseNum(v){
    var raw = String(v == null ? "" : v).trim();
    var negative = raw.charAt(0) === "-";
    var n = parseFloat(raw.replace(/[^0-9.]/g,""));
    if (isNaN(n)) return null;
    return negative ? -n : n;
  }
  function amount(id){
    var n = parseNum($(id).value);
    return n == null ? 0 : n;
  }
  function esc(v){
    return String(v == null ? "" : v)
      .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;").replace(/'/g,"&#039;");
  }
  function cite(label,url,detail){
    return '<span class="eob-cite">Source: <a href="' + esc(url) + '" target="_blank" rel="noopener noreferrer">'
      + esc(label) + '</a>' + (detail ? " · " + esc(detail) : "") + '</span>';
  }
  function setStatus(el,label,style){
    el.textContent = label;
    el.className = el.className.replace(/eob-g-w+/g,"").trim() + " " + STATUS_CLASS[style];
  }
  function cashGrid(items){
    return '<div class="eob-cash-grid">' + items.map(function(item){
      return '<div class="eob-cash-stat"><span>' + esc(item[0]) + '</span><strong>' + esc(item[1]) + '</strong></div>';
    }).join("") + '</div>';
  }

  /* ======================================================================
     Input plausibility. The tool used to multiply any base under 1,000 by
     1,000, so 999 became $999,000 while 1,000 stayed $1,000, and a stripped
     minus sign turned -10 into 10. Nothing is silently reinterpreted now:
     a value outside these ranges is refused with the reason.
     ====================================================================== */
  var LIMITS = {
    "eob-oe-base":       { label:"Annual base salary", min:10000, max:3000000, range:"$10,000 and $3,000,000",
                           hint:"Enter the full annual amount, for example 150000. Shorthand like 150 is no longer read as $150,000." },
    "eob-oe-guaranteed": { label:"Guaranteed annual bonus", min:0, max:2000000, range:"$0 and $2,000,000" },
    "eob-oe-bonus":      { label:"Target bonus", min:0, max:100, range:"0 and 100",
                           hint:"This field is a percentage of base, not a dollar amount." },
    "eob-oe-signon":     { label:"Sign-on bonus", min:0, max:2000000, range:"$0 and $2,000,000" },
    "eob-oe-shares":     { label:"Grant shares or options", min:0, max:1000000000, range:"0 and 1,000,000,000" },
    "eob-oe-fdshares":   { label:"Fully diluted shares", min:0, max:100000000000, range:"0 and 100,000,000,000" },
    "eob-oe-ownership":  { label:"Ownership percentage", min:0, max:100, range:"0 and 100" },
    "eob-oe-strike":     { label:"Strike price per share", min:0, max:100000, range:"$0 and $100,000" },
    "eob-oe-409a":       { label:"Latest 409A or common value", min:0, max:100000, range:"$0 and $100,000" },
    "eob-oe-preferred":  { label:"Latest preferred price", min:0, max:100000, range:"$0 and $100,000" },
    "eob-oe-grantvalue": { label:"Stated RSU or grant value", min:0, max:100000000, range:"$0 and $100,000,000" }
  };
  function validateInputs(){
    var problems = [];
    Object.keys(LIMITS).forEach(function(id){
      var el = $(id);
      if (!el) return;
      var raw = String(el.value == null ? "" : el.value).trim();
      if (raw === "") return;
      var rule = LIMITS[id];
      var n = parseNum(raw);
      if (n == null){
        problems.push(rule.label + " is not a number.");
        return;
      }
      if (n < 0){
        problems.push(rule.label + " cannot be negative.");
        return;
      }
      if (n < rule.min || n > rule.max){
        problems.push(rule.label + " must be between " + rule.range + "." + (rule.hint ? " " + rule.hint : ""));
      }
    });
    return problems;
  }

  function benchmarkFor(role,stage,location){
    var ea = data.executiveAssistant;
    if (role === "cos"){
      var cos = data.chiefOfStaff;
      return {
        kind:"median",
        median:cos.stageMedians[stage],
        label:cos.stageLabels[stage] + " observed median base",
        source:cos.stageSource.source,
        sourceUrl:cos.stageSource.sourceUrl,
        detail:"n=" + cos.stageSource.sample + " overall; stage cell n not published",
        note:"No location or experience multiplier is applied."
      };
    }
    if (role === "ea"){
      if (location !== "national"){
        var geo = ea.geography[location];
        return {
          kind:"band",
          low:geo.cSuiteLow,
          median:geo.cSuiteMedian,
          high:geo.cSuiteHigh,
          label:geo.label + " published executive-support market range",
          source:ea.cSuiteNational.source,
          sourceUrl:ea.cSuiteNational.sourceUrl,
          detail:"self-reported base; geographic cell n not disclosed",
          note:"Published market range, not verified local percentiles."
        };
      }
      return {
        kind:"band",
        low:ea.cSuiteNational.p25,
        median:ea.cSuiteNational.median,
        high:ea.cSuiteNational.p75,
        label:"National EA incumbent middle 50%",
        source:ea.cSuiteNational.source,
        sourceUrl:ea.cSuiteNational.sourceUrl,
        detail:"n≈" + ea.cSuiteNational.sample + " EAs; self-reported base",
        note:"P25 to P75 in a specialized executive-support network."
      };
    }
    if (role === "senior_ea"){
      return {
        kind:"mean",
        median:ea.titleMeans.senior_ea.meanBase,
        label:"Senior EA reported mean base",
        source:ea.independentNational.source,
        sourceUrl:ea.independentNational.sourceUrl,
        detail:"n=" + ea.independentNational.sample + " overall; title cell n not disclosed",
        note:"A contextual mean, not a median or range. No city adjustment is applied."
      };
    }
    var ops = data.executiveOperations.premium;
    return {
      kind:"band",
      low:ops.p25,
      median:ops.median,
      high:ops.p75,
      label:"Premium active Executive Operations postings",
      source:ops.source,
      sourceUrl:ops.sourceUrl,
      detail:"n=" + ops.sample + "; posted midpoint; $100k floor",
      note:"Premium opportunity market, not a national incumbent benchmark."
    };
  }

  function bonusCitation(role){
    if (role === "cos"){
      var c = data.chiefOfStaff.bonusContext;
      return "In a small CoS survey, " + pct(c.prevalence) + " received a bonus and recipients averaged "
        + c.averagePercentAmongRecipients + "% of base. "
        + cite(c.source,c.sourceUrl,"n=" + c.sample);
    }
    if (role === "ea" || role === "senior_ea"){
      var ea = data.executiveAssistant;
      return "C-Suite Assistants reports " + pct(ea.bonusContext.discretionaryShare) + " discretionary and "
        + pct(ea.bonusContext.guaranteedShare) + " guaranteed bonus. The independent survey reports a "
        + ea.bonusContext.independentAveragePercent + "% average bonus, but its denominator is unclear. "
        + cite(ea.cSuiteNational.source,ea.cSuiteNational.sourceUrl,"n≈" + ea.cSuiteNational.sample + " EAs")
        + " " + cite(ea.independentNational.source,ea.independentNational.sourceUrl,"n=" + ea.independentNational.sample + " overall");
    }
    return "No clean Executive Operations bonus benchmark is available. Treat the target as offer-specific and verify the payout basis and history.";
  }

  function evaluate(){
    var err = $("eob-oe-err");
    err.textContent = "";
    if (!data){
      err.textContent = "Compensation data is still loading. Try again in a moment.";
      return;
    }

    var role = $("eob-oe-role").value;
    var stage = $("eob-oe-stage").value;
    var location = $("eob-oe-tier").value;
    var equity = $("eob-oe-equity").value;
    var base = parseNum($("eob-oe-base").value);
    if (base == null){
      err.textContent = "Enter the annual base salary.";
      $("eob-oe-result").className = $("eob-oe-result").className.replace(" eob-show","");
      return;
    }
    var problems = validateInputs();
    if (problems.length){
      err.textContent = problems[0];
      $("eob-oe-result").className = $("eob-oe-result").className.replace(" eob-show","");
      return;
    }

    var guaranteed = amount("eob-oe-guaranteed");
    var targetPct = amount("eob-oe-bonus");
    var signon = amount("eob-oe-signon");
    var targetBonus = base * targetPct / 100;
    var annualBonusUsed = Math.max(guaranteed,targetBonus);
    var guaranteedFirstYear = base + guaranteed + signon;
    var targetAnnual = base + annualBonusUsed;
    var targetFirstYear = targetAnnual + signon;

    var benchmark = benchmarkFor(role,stage,location);
    var baseStyle,baseLabel,baseText,baseLine;
    if (benchmark.kind === "band"){
      baseLine = benchmark.label + ": " + money(benchmark.low) + " to " + money(benchmark.high) + "; midpoint/median " + money(benchmark.median) + ".";
      if (base < benchmark.low){
        baseStyle = "below";
        baseLabel = "Below observed band";
        baseText = "The offered base is " + money(benchmark.low - base) + " below the bottom of this observed comparison.";
      } else if (base > benchmark.high){
        baseStyle = "strong";
        baseLabel = "Above observed band";
        baseText = "The offered base is above the top of this observed comparison. Confirm that scope, level, and internal title match the pay.";
      } else {
        baseStyle = "solid";
        baseLabel = "Within observed band";
        baseText = "The offered base sits inside this observed comparison. Where it lands should track reporting line, scope, budget, and headcount authority.";
      }
    } else {
      baseLine = benchmark.label + ": " + money(benchmark.median) + ".";
      if (base < benchmark.median){
        baseStyle = "below";
        baseLabel = "Below reported " + benchmark.kind;
        baseText = "The offered base is " + money(benchmark.median - base) + " below the reported " + benchmark.kind + ". This is a reference point, not the bottom of a band.";
      } else {
        baseStyle = "strong";
        baseLabel = "At or above reported " + benchmark.kind;
        baseText = "The offered base is at or above the reported " + benchmark.kind + ". This does not establish that the whole package is competitive.";
      }
    }
    baseText += " " + benchmark.note;

    $("eob-oe-baseband").innerHTML = esc(baseLine) + "<br>" + cite(benchmark.source,benchmark.sourceUrl,benchmark.detail);
    $("eob-oe-basetext").textContent = baseText;
    setStatus($("eob-oe-g-base"),baseLabel,baseStyle);

    $("eob-oe-guaranteedtext").innerHTML = cashGrid([
      ["Base",money(base)],
      ["Guaranteed bonus",money(guaranteed)],
      ["Sign-on",money(signon)],
      ["Guaranteed first year",money(guaranteedFirstYear)]
    ]) + '<p>Guaranteed first-year cash includes the one-time sign-on bonus and does not assign value to target bonus or equity.</p>';
    setStatus($("eob-oe-g-guaranteed"),"Calculated","solid");

    /* The row is NOT called "target bonus". When a guaranteed minimum exceeds
       the target percentage, the figure shown is the guaranteed minimum, and
       calling that the target bonus misreports what the user entered. */
    var bonusBasis;
    if (guaranteed > 0 && guaranteed >= targetBonus){
      bonusBasis = "The guaranteed annual minimum of " + money(guaranteed) + " is larger than the "
        + targetPct + "% target on base (" + money(targetBonus) + "), so the guaranteed minimum is the figure used above. "
        + "This tool treats the guaranteed minimum as a floor that replaces the target amount, not as a payment that stacks on top of it. "
        + "If your offer pays the guaranteed minimum and the target bonus separately, add them yourself and confirm the wording in writing.";
    } else if (targetBonus > 0){
      bonusBasis = "The figure above is the " + targetPct + "% target on a base of " + money(base) + ". "
        + (guaranteed > 0
            ? "The guaranteed annual minimum of " + money(guaranteed) + " is lower, and it is treated as a floor inside that target rather than as an addition to it."
            : "No guaranteed annual minimum was entered, so none of this target is contractually assured.");
    } else {
      bonusBasis = "No target bonus percentage and no guaranteed annual minimum were entered, so no annual bonus is included in target cash.";
    }
    $("eob-oe-targettext").innerHTML = cashGrid([
      ["Bonus used for target cash",money(annualBonusUsed)],
      ["Target annual cash",money(targetAnnual)],
      ["Target first year",money(targetFirstYear)]
    ]) + '<p>' + esc(bonusBasis) + ' Sign-on appears only in first-year cash.</p><p>' + bonusCitation(role) + '</p>';
    setStatus($("eob-oe-g-target"),targetPct > 0 ? "Target entered" : (guaranteed > 0 ? "Guaranteed only" : "No bonus entered"),targetPct > 0 || guaranteed > 0 ? "solid" : "wait");

    evaluateEquityAndTerms({
      role:role,
      stage:stage,
      location:location,
      equity:equity,
      base:base,
      guaranteedFirstYear:guaranteedFirstYear,
      targetAnnual:targetAnnual,
      targetPct:targetPct,
      guaranteed:guaranteed,
      benchmark:benchmark,
      baseStyle:baseStyle,
      baseLabel:baseLabel
    });
  }

  function evaluateEquityAndTerms(ctx){
    var shares = amount("eob-oe-shares");
    var fdShares = amount("eob-oe-fdshares");
    var ownership = amount("eob-oe-ownership");
    var strike = amount("eob-oe-strike");
    var common409a = amount("eob-oe-409a");
    /* The result used to claim the 409A date had been checked while the form
       collected only the value. The date is collected now, and its age is
       stated rather than assumed. */
    var valuationDateEl = $("eob-oe-409a-date");
    var valuationDateRaw = valuationDateEl ? String(valuationDateEl.value || "").trim() : "";
    var valuationAge = monthsSince(valuationDateRaw);
    var preferred = amount("eob-oe-preferred");
    var grantValue = amount("eob-oe-grantvalue");
    var missingEquity = [];
    var equityReady = false;
    var ownershipCalc = ownership > 0 ? ownership : (shares > 0 && fdShares > 0 ? shares / fdShares * 100 : 0);
    var equityText = "";

    if (ctx.equity === "none"){
      equityText = "No equity is included. This is not automatically below market: "
        + pct(data.chiefOfStaff.equityContext.prevalence) + " held equity in a small CoS survey, while the EA surveys report equity/options for "
        + pct(data.executiveAssistant.equityContext.cSuiteShare) + " and "
        + pct(data.executiveAssistant.equityContext.independentShare)
        + " of respondents. Evaluate cash on its own and ask whether equity is available at the internal level.";
      setStatus($("eob-oe-g-equity"),"No equity entered","wait");
    } else if (ctx.equity === "options"){
      if (!(ownershipCalc > 0)) missingEquity.push("Ownership percentage, or both grant shares and fully diluted shares");
      if (!(strike > 0)) missingEquity.push("Strike price");
      if (!(common409a > 0)) missingEquity.push("Latest 409A/common share value");
      if (valuationAge === null) missingEquity.push("The date of that 409A valuation");
      else if (valuationAge < 0) missingEquity.push("A 409A valuation date that is not in the future");
      if (!$("eob-oe-t-vesting").checked) missingEquity.push("Vesting schedule and cliff");
      if (!$("eob-oe-t-window").checked) missingEquity.push("Post-termination exercise window");
      equityReady = missingEquity.length === 0;
      var ageNote = "";
      if (valuationAge !== null && valuationAge >= 0){
        ageNote = " The 409A valuation you entered is about " + valuationAge + " month" + (valuationAge === 1 ? "" : "s")
          + " old." + (valuationAge > 12
            ? " A 409A more than twelve months old is usually superseded, so ask whether a newer valuation exists before you rely on this spread."
            : "");
      }
      equityText = equityReady
        ? "The core inputs needed to discuss this private-option grant are present. Ownership is " + ownershipCalc.toFixed(3) + "%." + ageNote + " This still does not make the grant liquid, guaranteed, or comparable with cash."
        : "The grant cannot yet be evaluated responsibly. Treat its value as unknown until the missing items below are supplied." + ageNote;
      setStatus($("eob-oe-g-equity"),equityReady ? "Enough information" : "Missing information",equityReady ? "strong" : "wait");
    } else if (ctx.equity === "rsu"){
      if (!(grantValue > 0)) missingEquity.push("Stated grant value or a current share-price valuation");
      if (!$("eob-oe-t-vesting").checked) missingEquity.push("Vesting schedule");
      equityReady = missingEquity.length === 0;
      equityText = equityReady
        ? "A stated RSU value and vesting schedule are present. Confirm grant-date units, refresh policy, tax withholding, and what happens if employment ends."
        : "The RSU grant is missing information needed to compare it with the cash package.";
      setStatus($("eob-oe-g-equity"),equityReady ? "Enough information" : "Missing information",equityReady ? "strong" : "wait");
    } else {
      if (!(grantValue > 0 || ownershipCalc > 0)) missingEquity.push("A stated grant value or computable ownership percentage");
      if (!$("eob-oe-t-vesting").checked) missingEquity.push("Vesting schedule and cliff");
      equityReady = missingEquity.length === 0;
      equityText = equityReady ? "Basic grant information is present, but the security type and valuation rules still need confirmation." : "The security type or valuation information is incomplete.";
      setStatus($("eob-oe-g-equity"),equityReady ? "Partial information" : "Missing information",equityReady ? "solid" : "wait");
    }
    $("eob-oe-equitytext").textContent = equityText;
    var eqList = $("eob-oe-equitylist");
    eqList.innerHTML = "";
    missingEquity.forEach(function(item){
      var li = document.createElement("li");
      li.textContent = item;
      eqList.appendChild(li);
    });

    var scenarios = "";
    if (ctx.equity === "options" && shares > 0 && strike > 0 && common409a > 0){
      var commonSpread = Math.max(common409a - strike,0) * shares;
      scenarios = '<div class="eob-scenarios">'
        + '<div class="eob-scenario"><span>Zero-value case</span><strong>$0</strong></div>'
        + '<div class="eob-scenario"><span>409A spread</span><strong>' + money(commonSpread) + '</strong></div>';
      if (preferred > 0){
        scenarios += '<div class="eob-scenario"><span>Preferred-price spread</span><strong>' + money(Math.max(preferred - strike,0) * shares) + '</strong></div>';
      }
      scenarios += '</div><p class="eob-cite">Illustrative total-grant spread before vesting, taxes, exercise cost, dilution, preferences, and liquidity risk. Preferred price is not common-share cash value.</p>';
    }
    var equityCitation = "";
    if (ctx.role === "cos"){
      var cosEquity = data.chiefOfStaff.equityContext;
      equityCitation = '<p class="eob-cite">Incidence context: ' + pct(cosEquity.prevalence) + ' held equity in this small survey. '
        + cite(cosEquity.source,cosEquity.sourceUrl,"n=" + cosEquity.sample) + '</p>';
    } else if (ctx.role === "ea" || ctx.role === "senior_ea"){
      var eaEquity = data.executiveAssistant;
      equityCitation = '<p class="eob-cite">Incidence context: ' + pct(eaEquity.equityContext.cSuiteShare)
        + ' in C-Suite Assistants and ' + pct(eaEquity.equityContext.independentShare) + ' in the independent survey. '
        + cite(eaEquity.cSuiteNational.source,eaEquity.cSuiteNational.sourceUrl,"n≈" + eaEquity.cSuiteNational.sample + " EAs")
        + " " + cite(eaEquity.independentNational.source,eaEquity.independentNational.sourceUrl,"n=" + eaEquity.independentNational.sample + " overall") + '</p>';
    } else {
      equityCitation = '<p class="eob-cite">No role-specific Executive Operations equity band is used. Review the inputs with the <a href="https://carta.com/learn/equity/startup-equity-calculator/" target="_blank" rel="noopener noreferrer">Carta equity guide</a>.</p>';
    }
    $("eob-oe-scenarios").innerHTML = scenarios + equityCitation;
    renderTermsAndSummary(ctx,missingEquity,equityReady);
  }

  function renderTermsAndSummary(ctx,missingEquity,equityReady){
    var relevantTerms = TERMS.filter(function(t){
      if (t.optionsOnly && ctx.equity !== "options") return false;
      if (t.equityOnly && ctx.equity === "none") return false;
      return true;
    });
    var missingTerms = relevantTerms.filter(function(t){ return !$(t.id).checked; });
    var coveredCount = relevantTerms.length - missingTerms.length;
    var halfway = Math.ceil(relevantTerms.length / 2);
    setStatus(
      $("eob-oe-g-terms"),
      missingTerms.length === 0 ? "Complete" : (coveredCount >= halfway ? "Open items" : "Several open items"),
      missingTerms.length === 0 ? "strong" : (coveredCount >= halfway ? "solid" : "below")
    );
    $("eob-oe-termstext").textContent = "The offer addresses " + coveredCount + " of " + relevantTerms.length + " relevant terms.";
    var termsList = $("eob-oe-termslist");
    termsList.innerHTML = "";
    missingTerms.forEach(function(t){
      var li = document.createElement("li");
      li.textContent = t.name + ": " + t.why;
      termsList.appendChild(li);
    });

    var qs = [];
    missingEquity.forEach(function(item){
      if (qs.length < 2) qs.push("Can you provide: " + item.toLowerCase() + "?");
    });
    if (ctx.baseStyle === "below"){
      var target = ctx.benchmark.kind === "band" ? ctx.benchmark.low : ctx.benchmark.median;
      qs.push("Is there room to move base closer to " + money(target) + ", the named reference point, and if not, where is there flexibility?");
    }
    if (ctx.targetPct === 0 && ctx.guaranteed === 0) qs.push("Is an annual bonus available at this internal level, and what determines payout?");
    else qs.push("Is the annual bonus discretionary or formula-based, and what has it paid historically?");
    if (!$("eob-oe-t-severance").checked) qs.push("What severance applies if the principal leaves, the role changes, or employment ends?");
    if (!$("eob-oe-t-review").checked) qs.push("When is the first compensation review, and are refresh grants available?");
    if (!$("eob-oe-t-title").checked) qs.push("What internal level does this role map to?");
    if (qs.length < 3) qs.push("What does success look like in the first year, and what scope do I own outright?");
    qs = qs.slice(0,4);
    var qList = $("eob-oe-questions");
    qList.innerHTML = "";
    qs.forEach(function(q){
      var li = document.createElement("li");
      li.textContent = q;
      qList.appendChild(li);
    });

    var summary = ROLE_LABEL[ctx.role];
    if (ctx.role === "cos") summary += ", " + data.chiefOfStaff.stageLabels[ctx.stage];
    else if ((ctx.role === "ea" || ctx.role === "senior_ea") && ctx.location !== "national") summary += ", " + data.executiveAssistant.geography[ctx.location].label;
    $("eob-oe-summary").textContent = summary;
    $("eob-oe-overall").textContent = "This readout keeps the components separate: base is " + ctx.baseLabel.toLowerCase()
      + "; guaranteed first-year cash is " + money(ctx.guaranteedFirstYear)
      + "; target annual cash is " + money(ctx.targetAnnual)
      + "; and equity information is " + (ctx.equity === "none" ? "not included" : (equityReady ? "sufficient for a first-pass discussion" : "incomplete")) + ".";
    setStatus($("eob-oe-verdict"),"Component readout","solid");

    var panel = $("eob-oe-result");
    if (panel.className.indexOf("eob-show") === -1) panel.className += " eob-show";
    setTimeout(postHeight,60);
  }

  function updateConditionalFields(){
    var role = $("eob-oe-role").value;
    $("eob-oe-stage-wrap").classList.toggle("eob-hidden",role !== "cos");
    $("eob-oe-location-wrap").classList.toggle("eob-hidden",!(role === "ea" || role === "senior_ea"));
    $("eob-oe-equity-fields").classList.toggle("eob-hidden",$("eob-oe-equity").value === "none");
    setTimeout(postHeight,60);
  }

  function postHeight(){
    var h = root.scrollHeight;
    if (window.parent && window.parent !== window){
      window.parent.postMessage({type:"eob-offer-height",height:h},"*");
    }
  }

  /* ======================================================================
     Local persistence. Ported from the First 90 Days planner: same guarded
     localStorage handle, same "restore, then save on every change" shape.
     An offer is private, so nothing here leaves the browser. The email field
     in the newsletter form is deliberately excluded.
     ====================================================================== */
  var STORE_KEY = "eob-offer-v1";
  var mem = {};
  var LS = (function(){
    try {
      var t = "__eob_t__";
      window.localStorage.setItem(t,"1");
      window.localStorage.removeItem(t);
      return window.localStorage;
    } catch(e){ return null; }
  })();

  function loadState(){
    if (LS){
      try { return JSON.parse(LS.getItem(STORE_KEY) || "{}") || {}; }
      catch(e){ return {}; }
    }
    return mem;
  }
  function saveState(state){
    if (LS){
      try { LS.setItem(STORE_KEY,JSON.stringify(state)); } catch(e){ mem = state; }
    } else { mem = state; }
  }

  var state = loadState();
  if (!state.fields) state.fields = {};

  var savedFields = Array.prototype.slice.call(
    root.querySelectorAll("select[id], input[id]")
  ).filter(function(el){
    return el.id && el.id.indexOf("eob-oe-") === 0;
  });

  function captureState(){
    savedFields.forEach(function(el){
      state.fields[el.id] = (el.type === "checkbox") ? !!el.checked : el.value;
    });
    saveState(state);
  }

  function restoreState(){
    savedFields.forEach(function(el){
      var v = state.fields[el.id];
      if (v === undefined) return;
      if (el.type === "checkbox") el.checked = !!v;
      else el.value = v;
    });
  }

  restoreState();
  savedFields.forEach(function(el){
    el.addEventListener("change",captureState);
    if (el.tagName === "INPUT" && el.type === "text") el.addEventListener("input",captureState);
  });

  $("eob-oe-go").addEventListener("click",function(){
    captureState();
    state.evaluated = true;
    saveState(state);
    evaluate();
  });
  $("eob-oe-role").addEventListener("change",updateConditionalFields);
  $("eob-oe-equity").addEventListener("change",updateConditionalFields);
  updateConditionalFields();

  var printBtn = $("eob-oe-print");
  if (printBtn) printBtn.addEventListener("click",function(){ window.print(); });

  /* Clear: two-step confirm on the button itself. No confirm() dialog. */
  var clearBtn = $("eob-oe-clear");
  if (clearBtn){
    var armed = false, armTimer = null;
    clearBtn.addEventListener("click",function(){
      if (!armed){
        armed = true;
        clearBtn.textContent = "Tap again to clear";
        clearBtn.style.borderColor = "#7A2129";
        clearBtn.style.color = "#7A2129";
        armTimer = setTimeout(function(){
          armed = false;
          clearBtn.textContent = "Clear saved entries";
          clearBtn.style.borderColor = "";
          clearBtn.style.color = "";
        },4000);
        return;
      }
      clearTimeout(armTimer);
      armed = false;
      clearBtn.textContent = "Clear saved entries";
      clearBtn.style.borderColor = "";
      clearBtn.style.color = "";
      state = { fields:{} };
      saveState(state);
      savedFields.forEach(function(el){
        if (el.type === "checkbox") el.checked = false;
        else if (el.tagName === "SELECT") el.selectedIndex = 0;
        else el.value = "";
      });
      var panel = $("eob-oe-result");
      panel.className = panel.className.replace(" eob-show","");
      $("eob-oe-err").textContent = "";
      updateConditionalFields();
    });
  }

  fetch("compensation-data.json",{cache:"no-store"})
    .then(function(response){
      if (!response.ok) throw new Error("Data request failed");
      return response.json();
    })
    .then(function(payload){
      data = payload;
      $("eob-oe-go").disabled = false;
      $("eob-oe-go").textContent = "Evaluate this offer";
      $("eob-oe-data-version").textContent = "Compensation data version: " + data.updatedLabel + ".";
      // A restored session gets its readout back, not just its inputs. The
      // benchmark file has to be in hand first, so this runs here.
      if (state.evaluated && $("eob-oe-base").value) evaluate();
      postHeight();
    })
    .catch(function(){
      $("eob-oe-go").textContent = "Compensation data unavailable";
      $("eob-oe-err").textContent = "The benchmark file could not load. Refresh the page before evaluating an offer.";
      $("eob-oe-data-version").textContent = "Compensation data file unavailable.";
      postHeight();
    });

  if (window.ResizeObserver) new ResizeObserver(postHeight).observe(root);
  window.addEventListener("load",postHeight);
  window.addEventListener("resize",postHeight);
  root.addEventListener("change",function(){ setTimeout(postHeight,60); });

  var subForm = root.querySelector("#eob-subscribe");
  var subMsg = root.querySelector("#eob-sub-msg");
  if (subForm){
    var frame = document.createElement("iframe");
    frame.name = "eob-ml-frame";
    frame.style.display = "none";
    frame.setAttribute("aria-hidden","true");
    root.appendChild(frame);
    subForm.addEventListener("submit",function(){
      var btn = subForm.querySelector("button");
      if (btn){ btn.disabled = true; btn.textContent = "Sending..."; }
      setTimeout(function(){
        if (subMsg) subMsg.textContent = "You are in. Check your inbox for the next note.";
        subForm.reset();
        if (btn){ btn.disabled = false; btn.textContent = "Subscribe"; }
        postHeight();
      },900);
    });
  }
})();
