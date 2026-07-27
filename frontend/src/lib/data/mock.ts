export type WorkspaceKey = 'diagnose' | 'design' | 'assess';

export interface WorkspaceMeta {
	key: WorkspaceKey;
	label: string;
	verb: string;
	description: string;
	accentClass: string;
	accentHex: string;
}

export const workspaces: WorkspaceMeta[] = [
	{
		key: 'diagnose',
		label: 'Diagnose',
		verb: 'Reads the watershed',
		description: 'Live sensor and imagery overlays surface blockages, erosion, and flow anomalies as they happen.',
		accentClass: 'diagnose',
		accentHex: '#0d983b'
	},
	{
		key: 'design',
		label: 'Design',
		verb: 'Plans the intervention',
		description: 'Draft channel and structure geometry directly on terrain, with survey-grade precision underfoot.',
		accentClass: 'design',
		accentHex: '#d5b443'
	},
	{
		key: 'assess',
		label: 'Assess',
		verb: 'Scores the risk',
		description: 'Every design is scored against flood, cost, and compliance models before a shovel moves.',
		accentClass: 'assess',
		accentHex: '#3969a7'
	}
];

export interface RecentItem {
	id: string;
	title: string;
	sub: string;
	kind: 'project' | 'survey';
	progress: number;
	updated: string;
}

export const recentItems: RecentItem[] = [
	{ id: 'p-1042', title: 'Kondaveedu Basin Retrofit', sub: 'Diagnose  Sector 4', kind: 'project', progress: 68, updated: '12m ago' },
	{ id: 's-0231', title: 'Nallah 7 Flow Survey', sub: 'Field capture  Drone pass 3/3', kind: 'survey', progress: 91, updated: '41m ago' },
	{ id: 'p-1039', title: 'Palar Confluence Reinforcement', sub: 'Design  Structure v4', kind: 'project', progress: 34, updated: '2h ago' },
	{ id: 's-0229', title: 'Manjeera Bank Erosion Scan', sub: 'Field capture  Ground sensors', kind: 'survey', progress: 100, updated: '5h ago' }
];

export interface QuickAction {
	label: string;
	hint: string;
}

export const quickActions: QuickAction[] = [
	{ label: 'New diagnostic scan', hint: 'Diagnose' },
	{ label: 'Open design canvas', hint: 'Design' },
	{ label: 'Run risk assessment', hint: 'Assess' },
	{ label: 'Import survey data', hint: 'Field' }
];

export interface Metric {
	label: string;
	value: number;
	suffix?: string;
	trend: number[];
	accent: string;
}

export const metrics: Metric[] = [
	{ label: 'Active projects', value: 47, trend: [4, 6, 5, 8, 7, 9, 10], accent: '#0d983b' },
	{ label: 'Ongoing surveys', value: 23, trend: [8, 7, 9, 6, 8, 10, 9], accent: '#d5b443' },
	{ label: 'Completed assessments', value: 312, trend: [30, 33, 31, 36, 40, 38, 42], accent: '#3969a7' },
	{ label: 'Pending reviews', value: 9, trend: [12, 10, 11, 8, 9, 7, 9], accent: '#6b829e' }
];

export type ProjectStatus = 'Active' | 'In Review' | 'Survey' | 'Complete';

export interface GalleryProject {
	id: string;
	name: string;
	basin: string;
	coords: string;
	status: ProjectStatus;
	hue: string;
}

export const galleryProjects: GalleryProject[] = [
	{ id: 'g1', name: 'Kondaveedu Basin', basin: 'Krishna Sub-basin', coords: '16.31°N 80.05°E', status: 'Active', hue: '#4FD1C5' },
	{ id: 'g2', name: 'Palar Confluence', basin: 'Palar Basin', coords: '12.98°N 79.15°E', status: 'In Review', hue: '#A78BFA' },
	{ id: 'g3', name: 'Manjeera Corridor', basin: 'Godavari Sub-basin', coords: '17.85°N 78.03°E', status: 'Survey', hue: '#E8B75A' },
	{ id: 'g4', name: 'Nallah 7 Realignment', basin: 'Musi Basin', coords: '17.36°N 78.47°E', status: 'Complete', hue: '#6EE7DE' },
	{ id: 'g5', name: 'Tungabhadra Terrace', basin: 'Tungabhadra Basin', coords: '15.83°N 76.65°E', status: 'Active', hue: '#4FD1C5' }
];
