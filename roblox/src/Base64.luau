--!strict
-- Base64 -> buffer (islandGen chunk geometry is base64 text).
local Base64 = {}

local LOOKUP: { [number]: number } = {}
do
	local alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
	for i = 1, 64 do
		LOOKUP[string.byte(alphabet, i)] = i - 1
	end
end

function Base64.decode(s: string): buffer
	s = s:gsub("%s", "")
	local n = #s
	local pad = (string.byte(s, n) == 61 and 1 or 0) + (string.byte(s, n - 1) == 61 and 1 or 0)
	local len = n // 4 * 3 - pad
	local out = buffer.create(len)
	local o = 0
	for i = 1, n, 4 do
		local a, b, c, d = string.byte(s, i, i + 3)
		local v = LOOKUP[a] * 262144 + LOOKUP[b] * 4096 + (LOOKUP[c] or 0) * 64 + (LOOKUP[d] or 0)
		buffer.writeu8(out, o, bit32.rshift(v, 16))
		if o + 1 < len then
			buffer.writeu8(out, o + 1, bit32.band(bit32.rshift(v, 8), 255))
		end
		if o + 2 < len then
			buffer.writeu8(out, o + 2, bit32.band(v, 255))
		end
		o += 3
	end
	return out
end

return Base64
