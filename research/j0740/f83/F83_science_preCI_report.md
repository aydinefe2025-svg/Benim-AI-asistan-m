# A01.01.51 — F83 kaynak RNS EOS entalpi tutarlılığı ve gerçek iki-ağ GR C teyidi

- F80/BPS–MPA1 ayrı sayısal adayını temel alır; özgün JESTER mikrofiziği değildir.
- Başlangıç SHA-256: `f4a183661962acdddc7aebde3830116578feb6fba88a1a68c9fd57a993058675`. 1.213 satır orijinal dosya ve P/E kaynak tokenları aynen korunur.
- Doğrudan matematiksel denetim: her satırda `mu0=(epsilon+P)/(n exp(h))=930.4 MeV` olmasına rağmen 11 nedensel entalpi sınırı aralığı; bunun 8'i yalnız monotonluk sınırını da bozar. P-E çiftleri arası sekantlar nedensel.
- Yapıcı yanıt: her komşu basınç–enerji çifti arasında epsilon(P) tam doğrusal; `dh=log1p((1+s)*dP/(E0+P0))/(1+s)` (`s=dE/dP>=1`) tam analitik; `n=(E+P)/(mu0 exp(h))` ile yeniden kurulur. Yalnız H ve n değişir. Dolayısıyla açık aralıklar üzerinde cebirsel soğuk birinci yasa ve nedensellik sağlanır. Düğümde türev atlaması: C1 NOT_ESTABLISHED.
- Kaynak tabloda 11/8 aralık ihlali → yeniden inşa sonucunda 0/0. Yeni RNS EOS SHA-256 `99fc172310b06b2aa0a972320478853c84057c6d1e2810328f97e3c19c37309d`.
- Max absolute pseudo-enthalpy shift `6.969128636570392e-05`; max relative baryon density shift `6.968885798419588e-05`, yani yaklaşık yüzde 0.006969.
- 14/14 local fail-closed tests PASS including real source and synthetic adversarial, no physically unverified claim.
- Following source reconstruction, GitHub Actions will newly compile pinned C/RNS at 151x301 and 201x401 and solve actual new-EOS M=2.073 Msun, measured f=346.536369Hz roots and J, and compare side by side against original F81 C stars. Until real CI completes: NEW EOS C STARS NOT_RUN. No original F82 fixed-J turning point transfers to this altered EOS.
- Separate science limitations: BPS original tabulated composition/Gibbs phase order NOT_ESTABLISHED, continuous differentiability across piecewise nodes NOT_ESTABLISHED, global fixed-J and normal modes NOT_ESTABLISHED, native NICER/XMM X-PSI likelihood and 7 physical EOS Bayes NOT_RUN.
