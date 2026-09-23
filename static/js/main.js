
document.addEventListener("DOMContentLoaded", () => {
  const header = document.getElementById("siteHeader");
  const navToggle = document.querySelector(".nav-toggle");
  const nav = document.getElementById("mainNav");

  const setHeader = () => {
    if (header) header.classList.toggle("scrolled", window.scrollY > 10);
  };
  setHeader();
  window.addEventListener("scroll", setHeader, {passive:true});

  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    nav.querySelectorAll("a").forEach(a => a.addEventListener("click", () => {
      nav.classList.remove("open");
      navToggle.setAttribute("aria-expanded","false");
    }));
  }

  const revealObserver = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add("visible");
        obs.unobserve(entry.target);
      }
    });
  }, {threshold:.08, rootMargin:"0px 0px -35px"});
  document.querySelectorAll(".reveal").forEach(el => revealObserver.observe(el));

  const progressObserver = new IntersectionObserver((entries, obs) => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const fill = entry.target;
      const pct = Math.max(0, Math.min(100, Number(fill.dataset.progress || 0)));
      requestAnimationFrame(() => { fill.style.width = pct + "%"; });
      obs.unobserve(fill);
    });
  }, {threshold:.2});
  document.querySelectorAll(".progress-fill").forEach(el => progressObserver.observe(el));

  const counters = document.querySelectorAll(".animated-stat");
  counters.forEach(el => {
    const target = Number(el.dataset.target || 0);
    let started = false;
    const obs = new IntersectionObserver(entries => {
      if (!entries[0].isIntersecting || started) return;
      started = true;
      const type = el.dataset.statType || "number";
      const duration = 1200;
      const start = performance.now();
      const format = value => {
        if (type === "currency") return "₹" + Math.round(value).toLocaleString("en-IN");
        return Math.round(value).toLocaleString("en-IN");
      };
      const tick = now => {
        const p = Math.min(1, (now-start)/duration);
        const eased = 1 - Math.pow(1-p,3);
        el.textContent = format(target*eased);
        if (p < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      obs.disconnect();
    }, {threshold:.5});
    obs.observe(el);
  });

  const campaignSearch = document.getElementById("campaignSearch");
  const campaignFilters = document.getElementById("campaignFilters");
  const campaignGrid = document.getElementById("campaignGrid");
  const campaignCount = document.getElementById("campaignCount");
  const campaignSort = document.getElementById("campaignSort");

  if (campaignGrid && (campaignSearch || campaignFilters)) {
    const cards = Array.from(campaignGrid.querySelectorAll(".campaign-card"));
    let filter = "all";
    const apply = () => {
      const q = (campaignSearch?.value || "").trim().toLowerCase();
      let visible = cards.filter(card => {
        const category = card.dataset.category || "";
        const text = card.innerText.toLowerCase();
        return (filter === "all" || category.includes(filter)) && (!q || text.includes(q));
      });
      if (campaignSort) {
        const sort = campaignSort.value;
        visible.sort((a,b) => {
          const pa = Number(a.dataset.progress || 0), pb = Number(b.dataset.progress || 0);
          if (sort === "progress") return pb-pa;
          if (sort === "goal") {
            const ga = Number((a.innerText.match(/Goal ₹([\d,]+)/)||[])[1]?.replaceAll(",","") || 0);
            const gb = Number((b.innerText.match(/Goal ₹([\d,]+)/)||[])[1]?.replaceAll(",","") || 0);
            return ga-gb;
          }
          return 0;
        });
      }
      cards.forEach(c => c.style.display = "none");
      visible.forEach(c => { c.style.display = ""; campaignGrid.appendChild(c); });
      if (campaignCount) campaignCount.textContent = visible.length + " campaign" + (visible.length===1?"":"s");
    };
    campaignSearch?.addEventListener("input", apply);
    campaignSort?.addEventListener("change", apply);
    campaignFilters?.querySelectorAll(".filter-pill").forEach(btn => {
      btn.addEventListener("click", () => {
        campaignFilters.querySelectorAll(".filter-pill").forEach(x=>x.classList.remove("active"));
        btn.classList.add("active"); filter = btn.dataset.filter || "all"; apply();
      });
    });
  }

  const adminSearch = document.getElementById("adminCampaignSearch");
  const adminFilters = document.getElementById("adminFilters");
  const adminCards = Array.from(document.querySelectorAll(".admin-campaign-card"));
  if (adminCards.length && (adminSearch || adminFilters)) {
    let filter = "ALL";
    const applyAdmin = () => {
      const q = (adminSearch?.value || "").toLowerCase().trim();
      adminCards.forEach(card => {
        const okStatus = filter==="ALL" || card.dataset.status===filter;
        const okSearch = !q || (card.dataset.search||"").includes(q);
        card.style.display = okStatus && okSearch ? "" : "none";
      });
    };
    adminSearch?.addEventListener("input", applyAdmin);
    adminFilters?.querySelectorAll(".filter-pill").forEach(btn => btn.addEventListener("click",()=>{
      adminFilters.querySelectorAll(".filter-pill").forEach(x=>x.classList.remove("active"));
      btn.classList.add("active"); filter=btn.dataset.filter||"ALL"; applyAdmin();
    }));
  }

  document.querySelectorAll(".hero-visual").forEach(hero => {
    hero.addEventListener("mousemove", e => {
      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
      const r = hero.getBoundingClientRect();
      const x = (e.clientX-r.left)/r.width-.5, y=(e.clientY-r.top)/r.height-.5;
      hero.style.transform = `perspective(900px) rotateY(${x*2}deg) rotateX(${-y*2}deg)`;
    });
    hero.addEventListener("mouseleave", ()=>hero.style.transform="");
  });

  document.querySelectorAll("input[type=file]").forEach(input => {
    input.addEventListener("change", () => {
      const box = input.closest(".upload-box");
      if (box && input.files.length) {
        const small = box.querySelector("small");
        if (small) small.textContent = input.files[0].name;
        box.style.borderColor = "#83a9f4";
      }
    });
  });

  const toast = document.getElementById("uiToast");
  window.showCrowdToast = message => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(()=>toast.classList.remove("show"),2600);
  };
});
