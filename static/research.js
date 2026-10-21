let labels={general:{innovations:'创新点',improvements:'可改进方向',takeaways:'可学习与参考之处'}},names={general:'通用研读'};
export function configureResearch(config,plugins){labels={...labels,...config.analysis_labels};names={general:'通用研读',...Object.assign({},...plugins.map(p=>p.modes||{}))};}
export function analysisLabels(mode){return labels[mode]||labels.general;}
export function modeLabel(mode){return names[mode]||mode||'通用研读';}
