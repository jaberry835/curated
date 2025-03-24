import { TestBed } from '@angular/core/testing';

import { Aichat2ServiceService } from './aichat2.service.service';

describe('Aichat2ServiceService', () => {
  let service: Aichat2ServiceService;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(Aichat2ServiceService);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
