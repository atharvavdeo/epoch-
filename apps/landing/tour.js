/* Self-hosted Driver.js walkthrough. Illustrative demo only; no analysis calls. */
(() => {
  'use strict';
  const button = document.getElementById('start-walkthrough');
  if (!button || !window.driver?.js?.driver) return;
  let active, generation = 0;
  const steps = [
    ['#top','Every second has a story','Epoch connects possible retention drop-offs to understandable evidence. This hosted page is a backend-free seeded showcase.'],
    ['#problem','The problem','Post-publish dips show where people leave. Epoch helps creators inspect possible causes before their next edit.'],
    ['.problem .glass-card:nth-child(1)','Find the moment','Shared timestamps connect source passages, delivery, chapters and candidate findings.'],
    ['.problem .glass-card:nth-child(2)','Understand the mechanism','Check context and counter-explanations before treating a concern as an edit.'],
    ['.problem .glass-card:nth-child(3)','Creator control','Typed editorial opinions remain suggestions; the original source stays intact.'],
    ['#pipeline-panel','Video pipeline','Probe, audio extraction, speech and visual preparation feed shared grounded review. Missing vision is disclosed.','pipeline','video'],
    ['#pipeline-panel','Audio pipeline','Audio preparation and speech alignment join the same review path; there is no fabricated visual evidence.','pipeline','audio'],
    ['#pipeline-panel','Script pipeline','Plain scripts use estimated timing; cue-based transcripts retain supplied segments. No voice or camera measurements are invented.','pipeline','script'],
    ['#demo','Review workspace','Choose a sample and inspect the charts. Numbers, findings and transcript examples here are illustrative seeded data.'],
    ['#sample-picker','Video samples','Switch among the supplied Hindi Short, Hindi trailer and English example. Source links identify the originals.'],
    ['.demo-media','Audio example','The audio excerpt demonstrates a voice-first input without pretending to provide video analysis.','sample','audio'],
    ['.demo-media','Script example','The unrecorded script demonstrates the text-first path with illustrative timing.','sample','script'],
    ['.demo-media','Playable source','Play, pause or seek the supplied Short. Charts follow the selected sample; the hosted page starts no processing job.','sample','short'],
    ['.demo-kpis','Scenario numbers','Viewed percentage and watch seconds use seeded assumptions, not observed audience analytics.'],
    ['#demo-panel','Retention curves','Survival stays monotonic while departure pressure can fluctuate. Inspect the legend, assumptions and explanatory charts.','view','retention'],
    ['#demo-panel','Candidate findings','Review timestamps, source examples and alternative explanations. These are seeded illustrations.','view','findings'],
    ['#demo-panel','Transcript','Read the sample passage and its timestamps. Demo text is not a fresh transcription of the uploaded videos.','view','transcript'],
    ['#demo-panel','Jev routing','Keep, rewrite, shorten and review decisions illustrate confidence routing and deterministic guards. No Jev request is sent here.','view','jev'],
    ['#export-demo','Export the illustration','Download a seeded demo report. It is explicitly labelled and is not a new immutable analysis package.'],
    ['.principle-grid .glass-card:nth-child(1)','Assumption sensitivity','Changing baseline and rule strength changes a scenario. The range is not a confidence interval.'],
    ['.principle-grid .glass-card:nth-child(2)','Review is a valid result','Low-confidence decisions route to review. Shortening requires earlier supporting evidence.'],
    ['.principle-grid .glass-card:nth-child(3)','Traceability','The full local application records hashes, model identities and immutable packages with coverage disclosures.'],
    ['.principle-grid .glass-card:nth-child(4)','A suggestion is not an edit','Compare hypothetical cuts using both watch seconds and viewed percentage, then reanalyse the edited source.'],
    ['#motion-toggle','Motion control','Pause background motion here. Reduced-motion preferences also disable tour transitions.'],
    ['.shader-footer','Continue on GitHub','Explore the implementation, architecture and local setup in the repository. Use Escape to close this tour or arrow keys to move between steps.']
  ];
  button.addEventListener('click', () => {
    active?.destroy(); let busy = false; const token = ++generation; const original = document.activeElement;
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const tour = window.driver.js.driver({
      animate: !reduced, smoothScroll: !reduced, allowKeyboardControl: true, showProgress: true,
      popoverClass: 'epoch-tour', nextBtnText: 'Next', prevBtnText: 'Back', doneBtnText: 'Finish',
      steps: steps.map(([selector,title,description]) => ({element: () => document.querySelector(selector) || document.querySelector('#demo'),popover:{title,description,side:'bottom'}})),
      onNextClick: () => { const i = (tour.getActiveIndex() || 0) + 1; if(i >= steps.length) tour.destroy(); else void go(i); },
      onPrevClick: () => { void go(Math.max(0,(tour.getActiveIndex() || 0)-1)); },
      onDestroyed: () => { generation++; active = undefined; original?.focus(); }
    }); active = tour;
    async function go(i) {
      if(busy) return; busy = true;
      const [selector,,,type,value] = steps[i];
      if(type === 'pipeline') document.querySelector(`[data-pipeline="${value}"]`)?.click();
      if(type === 'view') document.querySelector(`[data-view="${value}"]`)?.click();
      if(type === 'sample') { const picker = document.getElementById('sample-picker'); picker.value = value; picker.dispatchEvent(new Event('change',{bubbles:true})); }
      for(let n=0;n<20 && !document.querySelector(selector) && token===generation;n++) await new Promise(r=>setTimeout(r,80));
      await new Promise(r=>setTimeout(r,60)); busy = false;
      if(token===generation) tour.drive(i);
    }
    void go(0);
  });
})();
