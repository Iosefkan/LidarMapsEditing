export function arraysToPCD(positions: Float32Array): string {
  const count = positions.length / 3
  let header = ''
  header += '# .PCD v.7 - Point Cloud Data file format\n'
  header += 'VERSION .7\n'
  header += 'FIELDS x y z\n'
  header += 'SIZE 4 4 4\n'
  header += 'TYPE F F F\n'
  header += 'COUNT 1 1 1\n'
  header += `WIDTH ${count}\n`
  header += 'HEIGHT 1\n'
  header += 'VIEWPOINT 0 0 0 1 0 0 0\n'
  header += `POINTS ${count}\n`
  header += 'DATA ascii\n'
  let body = ''
  for (let i = 0; i < positions.length; i += 3) {
    const x = positions[i]
    const y = positions[i + 1]
    const z = positions[i + 2]
    body += `${x} ${y} ${z}\n`
  }
  return header + body
}

// Binary PCD generator (little-endian). Produces header + binary float32 payload.
export function arraysToPCDBinary(positions: Float32Array): Uint8Array {
  const count = positions.length / 3
  const header =
    '# .PCD v.7 - Point Cloud Data file format\n' +
    'VERSION .7\n' +
    'FIELDS x y z\n' +
    'SIZE 4 4 4\n' +
    'TYPE F F F\n' +
    'COUNT 1 1 1\n' +
    `WIDTH ${count}\n` +
    'HEIGHT 1\n' +
    'VIEWPOINT 0 0 0 1 0 0 0\n' +
    `POINTS ${count}\n` +
    'DATA binary\n'

  // Body: little-endian float32 triples
  const bodyBuffer = new ArrayBuffer(positions.length * 4)
  const view = new DataView(bodyBuffer)
  for (let i = 0; i < positions.length; i++) {
    view.setFloat32(i * 4, positions[i], true)
  }

  const enc = new TextEncoder()
  const headerBytes = enc.encode(header)
  const bodyBytes = new Uint8Array(bodyBuffer)

  const out = new Uint8Array(headerBytes.length + bodyBytes.length)
  out.set(headerBytes, 0)
  out.set(bodyBytes, headerBytes.length)
  return out
}


