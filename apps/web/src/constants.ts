import { ProjectFile, FileType } from './types';

// Mock File Tree Data
export const MOCK_FILE_TREE: ProjectFile[] = [
  {
    id: 'root',
    name: 'Project Root',
    type: FileType.FOLDER,
    children: [
      {
        id: 'folder-arch',
        name: 'Architectural',
        type: FileType.FOLDER,
        children: [
          { id: 'f1', name: 'A-101 Floor Plan.pdf', type: FileType.PDF, category: 'Architectural' },
          { id: 'f2', name: 'A-102 Elevations.pdf', type: FileType.PDF, category: 'Architectural' },
        ]
      },
      {
        id: 'folder-elec',
        name: 'Electrical',
        type: FileType.FOLDER,
        children: [
          { id: 'f3', name: 'E-201 Lighting.pdf', type: FileType.PDF, category: 'Electrical' },
        ]
      },
      {
        id: 'folder-struct',
        name: 'Structural',
        type: FileType.FOLDER,
        children: [
           { id: 'f4', name: 'S-101 Foundation.pdf', type: FileType.PDF, category: 'Structural' },
        ]
      },
      {
        id: 'folder-misc',
        name: 'Site Photos',
        type: FileType.FOLDER,
        children: [
          { id: 'img1', name: 'Site_Overview.jpg', type: FileType.IMAGE },
        ]
      }
    ]
  }
];

export const SAMPLE_IMAGE_URL = "https://picsum.photos/1200/1600"; // Portrait aspect ratio for PDF simulation

export const MOCK_HISTORY = [
  { id: '1', title: 'Electrical conduits on A-101', date: new Date(Date.now() - 1000000) },
  { id: '2', title: 'HVAC clash detection', date: new Date(Date.now() - 5000000) },
];
