import {initHistory} from './history.js';
export function activate(ctx) {
  const style=document.createElement('link');style.rel='stylesheet';style.href='/plugins/architecture-history/history.css';document.head.append(style);
  const section=document.createElement('section');section.id='view-history';section.className='view';document.querySelector('#view-library').parentElement.append(section);
  const nav=document.createElement('button');nav.className='nav-item';nav.dataset.view='history';nav.innerHTML=ctx.icon('book')+'<span>建筑史研究</span>';document.querySelector('.main-nav').append(nav);
  const ui=initHistory(ctx);ctx.registerView('history','建筑史研究',ui);
  const button=document.createElement('button');button.className='button outline small';button.textContent='摘录史料';button.onclick=()=>ui.fromReader();document.querySelector('#readerKnowledge').after(button);
}
