import { beforeAll, vi } from 'vitest'

// Mock Canvas API for tests (jsdom doesn't implement getContext)
beforeAll(() => {
  // Mock HTMLCanvasElement.getContext
  // @ts-expect-error - Mocking canvas for test environment
  HTMLCanvasElement.prototype.getContext = vi.fn((contextId: string) => {
    if (contextId === '2d') {
      return {
        fillRect: vi.fn(),
        clearRect: vi.fn(),
        strokeRect: vi.fn(),
        fillText: vi.fn(),
        strokeText: vi.fn(),
        measureText: vi.fn(() => ({ width: 0 })),
        beginPath: vi.fn(),
        closePath: vi.fn(),
        moveTo: vi.fn(),
        lineTo: vi.fn(),
        bezierCurveTo: vi.fn(),
        quadraticCurveTo: vi.fn(),
        arc: vi.fn(),
        arcTo: vi.fn(),
        ellipse: vi.fn(),
        rect: vi.fn(),
        fill: vi.fn(),
        stroke: vi.fn(),
        clip: vi.fn(),
        save: vi.fn(),
        restore: vi.fn(),
        translate: vi.fn(),
        rotate: vi.fn(),
        scale: vi.fn(),
        setTransform: vi.fn(),
        resetTransform: vi.fn(),
        createLinearGradient: vi.fn(() => ({
          addColorStop: vi.fn()
        })),
        createRadialGradient: vi.fn(() => ({
          addColorStop: vi.fn()
        })),
        createPattern: vi.fn(),
        drawImage: vi.fn(),
        createImageData: vi.fn(() => ({ data: new Uint8ClampedArray(4) })),
        getImageData: vi.fn(() => ({ data: new Uint8ClampedArray(4) })),
        putImageData: vi.fn(),
        setLineDash: vi.fn(),
        getLineDash: vi.fn(() => []),
        lineCap: 'round',
        lineJoin: 'round',
        lineWidth: 1,
        miterLimit: 10,
        strokeStyle: '#000000',
        fillStyle: '#000000',
        font: '10px sans-serif',
        textAlign: 'start',
        textBaseline: 'alphabetic',
        direction: 'ltr',
        globalAlpha: 1,
        globalCompositeOperation: 'source-over',
        filter: '',
        imageSmoothingEnabled: true,
        imageSmoothingQuality: 'low',
        canvas: {
          width: 400,
          height: 300,
          toDataURL: vi.fn(() => 'data:image/png;base64,mock')
        }
      } as unknown as CanvasRenderingContext2D
    }
    return null
  })

  // Mock HTMLCanvasElement.toDataURL
  HTMLCanvasElement.prototype.toDataURL = vi.fn((type?: string) => {
    return `data:${type || 'image/png'};base64,mockcanvasdata`
  })
})