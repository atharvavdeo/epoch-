import { Link } from 'react-router';
import { Dock } from '../components/Dock';
const samples = [
 ['Video · Hindi Short','Jio new device','355132ce-41b3-5ac2-ab11-76c786ec678d','24-second sample with saved transcript, delivery and retention scenario.'],
 ['Video · Hindi trailer','Prahaar trailer','97d1bc9b-1efc-5ece-8c8d-e0e14b40d126','Three-minute sample with chapters, findings and saved second opinions.'],
 ['Video · English','Ontology vs metadata','de3d436e-3243-53bd-a952-cdb989de78a2','Educational sample with shots, sampled OCR and detailed analysis.'],
 ['Audio · English','Voice-first excerpt','932cae17-a4f4-5653-80d7-da7a47d0fd44','40-second audio sample with speech and sound measurements.'],
 ['Script · English','Catalogue metadata script','f2ab5388-7bf5-5dbf-ad54-d505a4b9946b','Text-first review with estimated timing; no invented audio or visual signals.'],
];
export default function NewDemo() {
 return <div className="shell onboarding"><div className="header"><Link to="/">← Projects</Link><div className="title"><h1>Choose a sample</h1></div><span /></div>
 <ol className="stepper" aria-label="Demo workflow"><li className="on"><span>1 · Choose a source</span></li><li><span>2 · Open saved analysis</span></li><li><span>3 · Review and export</span></li></ol>
 <section className="card step-card"><h2>Video, audio or script</h2><p className="note" style={{margin:'12px 0 24px'}}>This hosted workspace uses prepared public samples. No file is uploaded and no new processing job is started. Choose a sample to explore the complete review interface.</p>
 <div className="demo-sample-grid">{samples.map(([kind,title,run,description])=><Link key={run} to={`/runs/${run}`}><small>{kind}</small><h3>{title}</h3><p>{description}</p><span>Open review →</span></Link>)}</div>
 <p className="note" style={{marginTop:24}}>For fresh uploads, script analysis or cloud questions, <a href="https://github.com/atharvavdeo/epoch-" target="_blank" rel="noopener noreferrer">run Epoch locally</a>.</p>
 </section><Dock active="new" /></div>;
}
