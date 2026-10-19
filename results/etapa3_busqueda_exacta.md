# Etapa 3 - Recuperación mediante búsqueda exacta

Colección: 523 fragmentos. Top-5 por consulta. Tiempos = mediana de 5 ejecuciones.

## Complejidad por algoritmo

| Algoritmo | Complejidad |
|---|---|
| Ingenuo (fuerza bruta) | O(m) por patrón y O(n·m) peor caso por texto |
| KMP | O(m) preproceso (una vez) + O(n) por texto |
| Función Z | O(n + m) por texto |
| Rabin-Karp (rolling hash) | O(m) preproceso + O(n) esperado por texto (O(n·m) peor caso) |
| Arreglo de sufijos | O(m log N + occ) por patrón, sin recorrer los fragmentos |

n = longitud del fragmento preprocesado, m = longitud del patrón, N = términos de toda la colección, occ = número de apariciones. Con k patrones y C candidatos, una consulta cuesta O(k·Σ n_i) con los algoritmos de recorrido y O(k·m log N) con el arreglo de sufijos.

## Consulta 1: "What is mentioned about the Great Red Spot and storms on Jupiter?"

- **Términos:** great, red, spot, storm, jupit
- **Patrones (términos + frases):** great, red, spot, storm, jupit, great red, red spot, spot storm, storm jupit
- **Fragmentos examinados:** 178 de 523 (filtrados con el índice invertido); con coincidencias: 178

| Algoritmo | Tiempo (ms) | Top-5 (ids) |
|---|---:|---|
| Ingenuo (fuerza bruta) | 14.490 | [213, 212, 200, 173, 174] |
| KMP | 10.191 | [213, 212, 200, 173, 174] |
| Función Z | 34.737 | [213, 212, 200, 173, 174] |
| Rabin-Karp (rolling hash) | 34.661 | [213, 212, 200, 173, 174] |
| Arreglo de sufijos | 0.358 | [213, 212, 200, 173, 174] |
| KMP sin índice (recorre todo) | 25.032 | [213, 212, 200, 173, 174] |

| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |
|---|---:|---:|---|---|---|
| 1 | 41.398 | 100% | Jupiter Facts > Atmosphere | great:3, red:3, spot:4, storm:3, jupit:2, great red:3, red spot:3 | The findings also indicate these **storms** are far taller than expected, with some extending 60 miles (100 kilometers) below the cloud tops and others, including the **Great** **Red** **Spot**, extending over 200 miles (350 kilometers). This surprising discovery demonstrates that the vortices cover regions beyond thos… |
| 2 | 27.881 | 100% | Jupiter Facts > Atmosphere | great:1, red:2, spot:2, storm:1, jupit:1, great red:1, red spot:2 | More recently, three smaller ovals merged to form the Little **Red** **Spot**, about half the size of its larger cousin. Findings from NASA’s Juno probe released in October 2021 provide a fuller picture of what’s going on below those clouds. Data from Juno shows that **Jupiter’s** cyclones are warmer on top, with lower… |
| 3 | 27.233 | 100% | Jupiter Facts > Introduction / Namesake | great:1, red:1, spot:1, storm:1, jupit:5, great red:1, red spot:1 | **Jupiter's** signature stripes and swirls are actually cold, windy clouds of ammonia and water, floating in an atmosphere of hydrogen and helium. The dark orange stripes are called belts, while the lighter bands are called zones, and they flow east and west in opposite directions. **Jupiter’s** iconic **Great** **Red*… |
| 4 | 25.585 | 100% | Juno Mission > Scientific Discoveries and Results | great:1, red:1, spot:1, storm:1, jupit:5, great red:1, red spot:1 | The now-departed Galileo spacecraft dropped a probe into **Jupiter’s** atmosphere in 1995 and found the place where it entered to be strangely dry, with one-tenth the water that scientists expected. Juno solved the mystery, showing that water is much more abundant nearer **Jupiter’s** equator. High-voltage electrical c… |
| 5 | 25.419 | 100% | Juno Mission > Scientific Discoveries and Results | great:2, red:1, spot:2, storm:1, jupit:1, great red:1, red spot:1 | Maybe the most iconic **storm** in the solar system, **Jupiter’s** **Great** **Red** **Spot** has been swirling for centuries. But it appears to be slowly shrinking, from twice Earth’s size in 1979 to 1.3 times now. Juno plumbed the depths of this signature cyclone, showing that its roots run 200 miles (320 kilometers)… |

## Consulta 2: "When was Pluto discovered and when was it reclassified as a dwarf planet?"

- **Términos:** pluto, discov, reclassifi, dwarf, planet
- **Patrones (términos + frases):** pluto, discov, reclassifi, dwarf, planet, pluto discov, discov reclassifi, reclassifi dwarf, dwarf planet
- **Fragmentos examinados:** 318 de 523 (filtrados con el índice invertido); con coincidencias: 318

| Algoritmo | Tiempo (ms) | Top-5 (ids) |
|---|---:|---|
| Ingenuo (fuerza bruta) | 22.729 | [386, 385, 384, 47, 387] |
| KMP | 16.108 | [386, 385, 384, 47, 387] |
| Función Z | 51.182 | [386, 385, 384, 47, 387] |
| Rabin-Karp (rolling hash) | 61.664 | [386, 385, 384, 47, 387] |
| Arreglo de sufijos | 0.522 | [386, 385, 384, 47, 387] |
| KMP sin índice (recorre todo) | 24.659 | [386, 385, 384, 47, 387] |

| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |
|---|---:|---:|---|---|---|
| 1 | 31.405 | 100% | Pluto Facts > Introduction | pluto:6, discov:1, reclassifi:1, dwarf:3, planet:4, reclassifi dwarf:1, dwarf planet:3 | **Pluto** is a complex and mysterious world with mountains, valleys, plains, craters, and glaciers. It is located in the distant Kuiper Belt. **Discovered** in 1930, **Pluto** was long considered our solar system's ninth **planet**. But after the discovery of similar worlds deeper in the Kuiper Belt, **Pluto** was **re… |
| 2 | 27.318 | 80% | Pluto Facts > Dwarf Planets | pluto:2, reclassifi:1, dwarf:1, planet:2, reclassifi dwarf:1, dwarf planet:1 | Why is **Pluto** no longer a **planet**? **Pluto** was **reclassified** as a **dwarf** **planet** in 2006 by the International Astronomical Union because other objects might cross its orbit.… |
| 3 | 25.078 | 80% | About the Planets > Ceres Facts / Pluto Facts / Haumea Facts / Makemake Facts / Eris Facts / Planet Sizes and Locations in Our Solar System / Is There Another Planet in the Solar System? / Temperatures Across Our Solar System | pluto:4, reclassifi:1, dwarf:5, planet:11, reclassifi dwarf:1, dwarf planet:5 | **Dwarf** **planet** Ceres is the largest object in the asteroid belt between Mars and Jupiter, and it's the only **dwarf** **planet** in the inner solar system. **Pluto** was long considered our solar system's ninth **planet**. It was **reclassified** as a **dwarf** **planet** in 2006 by the International Astronomical… |
| 4 | 16.874 | 80% | Ceres Facts > Introduction / Namesake | pluto:1, discov:1, dwarf:4, planet:4, dwarf planet:4 | **Dwarf** **planet** Ceres is the largest object in the asteroid belt between Mars and Jupiter, and it's the only **dwarf** **planet** located in the inner solar system. It was the first member of the asteroid belt to be **discovered** when Giuseppe Piazzi spotted it in 1801. When NASA's Dawn arrived in 2015, Ceres bec… |
| 5 | 11.478 | 60% | Pluto Facts > Introduction | pluto:6, dwarf:2, planet:2, dwarf planet:2 | According to the 2006 IAU Resolution, "a **dwarf** **planet** is an object in orbit around the Sun that is large enough to pull itself into a nearly round shape but has not been able to clear its orbit of debris." The IAU stated that **Pluto** falls into the **dwarf** **planet** category because it is located in a part… |

## Consulta 3: "What do we know about the moons of Mars, Phobos and Deimos?"

- **Términos:** know, moon, mar, phobo, deimo
- **Patrones (términos + frases):** know, moon, mar, phobo, deimo, know moon, moon mar, mar phobo, phobo deimo
- **Fragmentos examinados:** 250 de 523 (filtrados con el índice invertido); con coincidencias: 250

| Algoritmo | Tiempo (ms) | Top-5 (ids) |
|---|---:|---|
| Ingenuo (fuerza bruta) | 16.504 | [272, 273, 264, 306, 246] |
| KMP | 11.881 | [272, 273, 264, 306, 246] |
| Función Z | 36.080 | [272, 273, 264, 306, 246] |
| Rabin-Karp (rolling hash) | 41.606 | [272, 273, 264, 306, 246] |
| Arreglo de sufijos | 0.397 | [272, 273, 264, 306, 246] |
| KMP sin índice (recorre todo) | 24.745 | [272, 273, 264, 306, 246] |

| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |
|---|---:|---:|---|---|---|
| 1 | 38.837 | 80% | Mars Facts > Moons | moon:3, mar:4, phobo:4, deimo:3, mar phobo:1, phobo deimo:1 | **Mars** has two small **moons**, **Phobos** and **Deimos**, that may be captured asteroids. They're potato-shaped because they have too little mass for gravity to make them spherical. The **moons** get their names from the horses that pulled the chariot of the Greek god of war, Ares (whose Roman counterpart is **Mars*… |
| 2 | 10.286 | 40% | Mars Facts > Rings | mar:2, phobo:1 | **Mars** has no rings. However, in 50 million years when **Phobos** crashes into **Mars** or breaks apart, it could create a dusty ring around the Red Planet.… |
| 3 | 9.547 | 60% | Mars Exploration > Humans to Mars | know:1, moon:1, mar:2, moon mar:1 | Like the **Moon**, **Mars** is a rich destination for scientific discovery and a driver of technologies that will enable humans to travel and explore far from Earth. **Mars** remains our horizon goal for human exploration because it is one of the only other places we **know** in the solar system where life may have exi… |
| 4 | 7.201 | 40% | Moon Facts > How the Moon Got Its Name | know:1, moon:6, know moon:1 | Our **Moon** shares a name with all **moons** simply because people didn't **know** other **moons** existed until Galileo Galilei discovered four **moons** orbiting Jupiter in 1610. In Latin, the **Moon** was called Luna, which is the main adjective for all things **Moon**-related: lunar.… |
| 5 | 6.955 | 40% | Mars Exploration > Introduction | know:1, mar:1 | **Mars** is the fourth planet from the Sun, and the seventh largest. It’s the only planet we **know** of inhabited entirely by robots.… |

## Consulta 4: "What lies beneath the ice of Europa and when did Europa Clipper launch?"

- **Términos:** li, beneath, ic, europa, clipper, launch
- **Patrones (términos + frases):** li, beneath, ic, europa, clipper, launch, li beneath, beneath ic, ic europa, europa clipper, clipper launch
- **Fragmentos examinados:** 123 de 523 (filtrados con el índice invertido); con coincidencias: 123

| Algoritmo | Tiempo (ms) | Top-5 (ids) |
|---|---:|---|
| Ingenuo (fuerza bruta) | 11.710 | [111, 138, 106, 183, 204] |
| KMP | 8.205 | [111, 138, 106, 183, 204] |
| Función Z | 25.443 | [111, 138, 106, 183, 204] |
| Rabin-Karp (rolling hash) | 31.669 | [111, 138, 106, 183, 204] |
| Arreglo de sufijos | 0.260 | [111, 138, 106, 183, 204] |
| KMP sin índice (recorre todo) | 29.171 | [111, 138, 106, 183, 204] |

| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |
|---|---:|---:|---|---|---|
| 1 | 31.746 | 83% | Europa Facts > Facts About Europa | li:1, beneath:1, europa:4, clipper:1, launch:1, li beneath:1, europa clipper:1 | **Europa** is the fourth largest of Jupiter’s moons. It's the sixth-closest moon to the planet. **Europa** may be one of the most promising places in our solar system to find present-day environments suitable for some form of life beyond Earth. Scientists believe a saltwater ocean **lies** **beneath** its icy shell, ho… |
| 2 | 22.500 | 67% | Juno Mission > NASA’s Juno Measures Thickness of Europa’s Ice Shell | li:1, beneath:1, ic:3, europa:3, li beneath:1, beneath ic:1 | New insights into Jupiter’s icy moon, a candidate in the search for habitable worlds Data from NASA’s Juno mission has provided new insights into the thickness and subsurface structure of the icy shell encasing Jupiter’s moon **Europa**. Slightly smaller than Earth’s moon, **Europa** is one of the solar system’s highes… |
| 3 | 18.073 | 50% | Europa Clipper > What Will Europa Clipper Do? / Science Goals | europa:7, clipper:4, launch:1, europa clipper:4 | **Europa** **Clipper** will try to determine if Jupiter's icy moon **Europa** currently has habitable conditions. **Europa** **Clipper** lifted off aboard a SpaceX Falcon Heavy rocket from **Launch** Complex 39A at Kennedy Space Center in Florida at 12:06 p.m. EDT on Oct. 14, 2024. **Europa** **Clipper** is traveling 1… |
| 4 | 17.512 | 50% | Juno Mission > Europa Clipper | beneath:1, europa:3, clipper:1, europa clipper:1 | Scheduled to reach Jupiter's moon **Europa** in 2030, this NASA mission will search **beneath** **Europa's** icy surface for signs of life. Learn More About **Europa** and the **Clipper** Mission… |
| 5 | 16.282 | 67% | Jupiter Facts > Moons | beneath:1, europa:3, clipper:1, launch:1, europa clipper:1 | With four large moons and many smaller moons, Jupiter forms a kind of miniature solar system. Jupiter has 115 moons that are officially recognized by the International Astronomical Union. The four largest moons – Io, **Europa**, Ganymede, and Callisto – were first observed by the astronomer Galileo Galilei in 1610 usin… |

## Consulta 5: "What is the atmosphere of Venus made of?"

- **Términos:** atmospher, venu, made
- **Patrones (términos + frases):** atmospher, venu, made, atmospher venu, venu made
- **Fragmentos examinados:** 145 de 523 (filtrados con el índice invertido); con coincidencias: 145

| Algoritmo | Tiempo (ms) | Top-5 (ids) |
|---|---:|---|
| Ingenuo (fuerza bruta) | 6.974 | [483, 498, 482, 501, 480] |
| KMP | 4.900 | [483, 498, 482, 501, 480] |
| Función Z | 15.225 | [483, 498, 482, 501, 480] |
| Rabin-Karp (rolling hash) | 19.819 | [483, 498, 482, 501, 480] |
| Arreglo de sufijos | 0.201 | [483, 498, 482, 501, 480] |
| KMP sin índice (recorre todo) | 14.617 | [483, 498, 482, 501, 480] |

| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |
|---|---:|---:|---|---|---|
| 1 | 13.365 | 100% | Venus Facts > Potential for Life | atmospher:2, venu:4, made:1 | The most likely explanations focus on fine particles, ice crystals, or even a chemical compound called iron chloride. Although it's much less likely, another possibility considered by scientists who study astrobiology is that these streaks could be **made** up of microbial life, **Venus**-style. Astrobiologists note th… |
| 2 | 11.802 | 100% | Venus Facts > Surface | atmospher:1, venu:4, made:1 | **Venus** is the hottest planet in our solar system, with surface temperatures about 872 degrees Fahrenheit (467 Celsius). And **atmospheric** pressure at the surface squeezes with the same force as being more than 3,000 feet underwater on Earth (930 meters). The Soviet Union sent a series of probes to **Venus** betwee… |
| 3 | 10.781 | 100% | Venus Facts > Potential for Life | atmospher:1, venu:3, made:1 | Thirty miles up (about 50 kilometers) from the surface of **Venus** temperatures range from 86 to 158 Fahrenheit (30 to 70 Celsius). This temperature range could accommodate Earthly life, such as “extremophile” microbes. And **atmospheric** pressure at that height is similar to what we find on Earth’s surface. At the t… |
| 4 | 9.145 | 67% | Venus Facts > Atmosphere | atmospher:4, venu:3 | **Venus**’ **atmosphere** is one of extremes. With the hottest surface in the solar system, apart from the Sun itself, **Venus** is hotter even than the innermost planet, charbroiled Mercury. The **atmosphere** is mostly carbon dioxide — the same gas drives the greenhouse effect on both **Venus** and Earth — with dense… |
| 5 | 8.686 | 67% | Venus Facts > Introduction | atmospher:2, venu:5 | **Venus** is the second planet from the Sun, and Earth's closest planetary neighbor. **Venus** is the third brightest object in the sky after the Sun and Moon. **Venus** spins slowly in the opposite direction from most planets. **Venus** is similar in structure and size to Earth, and is sometimes called Earth's evil tw… |

## Consulta 6: "When did Voyager 1 reach interstellar space?"

- **Términos:** voyag, 1, reach, interstellar, space
- **Patrones (términos + frases):** voyag, 1, reach, interstellar, space, voyag 1, 1 reach, reach interstellar, interstellar space
- **Fragmentos examinados:** 165 de 523 (filtrados con el índice invertido); con coincidencias: 165

| Algoritmo | Tiempo (ms) | Top-5 (ids) |
|---|---:|---|
| Ingenuo (fuerza bruta) | 13.492 | [504, 423, 363, 505, 130] |
| KMP | 9.658 | [504, 423, 363, 505, 130] |
| Función Z | 30.935 | [504, 423, 363, 505, 130] |
| Rabin-Karp (rolling hash) | 36.356 | [504, 423, 363, 505, 130] |
| Arreglo de sufijos | 0.284 | [504, 423, 363, 505, 130] |
| KMP sin índice (recorre todo) | 24.110 | [504, 423, 363, 505, 130] |

| # | Puntuación | Cobertura | Documento > sección | Coincidencias | Fragmento |
|---|---:|---:|---|---|---|
| 1 | 31.630 | 80% | Voyager Mission > Introduction / NASA Engineers Help Prolong Voyager 2’s Science Mission / Mission Updates | voyag:7, 1:3, reach:3, interstellar:1, voyag 1:3, 1 reach:1, reach interstellar:1 | **Voyager** **1** and its twin **Voyager** 2 are the only spacecraft ever to operate outside the heliosphere, the protective bubble of particles and magnetic fields generated by the Sun. **Voyager** **1** **reached** the **interstellar** boundary in 2012, while **Voyager** 2 (traveling slower and in a different directi… |
| 2 | 19.201 | 60% | Solar System Facts > Size and Distance | voyag:6, 1:3, interstellar:2, voyag 1:3 | The heliosphere is the bubble created by the solar wind – a stream of electrically charged gas blowing outward from the Sun in all directions. The boundary where the solar wind is abruptly slowed by pressure from **interstellar** gases is called the termination shock. This edge occurs between 80-100 astronomical units.… |
| 3 | 17.429 | 80% | Oort Cloud Facts > Scale and Distance | 1:1, reach:3, interstellar:2, space:1, interstellar space:1 | Even if you could travel at the speed of light (about 671 million miles per hour, or **1** billion kilometers per hour), a trip to the Oort Cloud would require that you pack for a lengthy expedition. When light leaves the Sun, it takes a little over eight minutes to **reach** Earth, and about 4.5 hours to **reach** Nep… |
| 4 | 14.567 | 60% | Voyager Mission > The Interstellar Mission / The Golden Record | voyag:1, interstellar:1, space:1, interstellar space:1 | After completing the first in-depth reconnaissance of the outer planets, the twin **Voyagers** are on a new mission to chart the edge of **interstellar** **space**. The contents of the golden record were selected for NASA by a committee led by Carl Sagan of Cornell University.… |
| 5 | 13.009 | 60% | JPL Solar System > Solar System Exploration at JPL | voyag:3, interstellar:1, space:3, interstellar space:1 | Spacecraft managed by JPL for NASA have visited every planet in our solar system. This daunting accomplishment began when the JPL-built Mariner 2 spacecraft flew past Venus in 1962. Since then, many NASA **space** missions have explored the other planets and some of their many moons, as well as asteroids and comets. Th… |

## Limitaciones de la búsqueda exacta

| Tipo | Pregunta | Términos | Recuperados | Top-1 | Puntuación top-1 |
|---|---|---|---:|---|---:|
| literal | Who discovered Uranus? | discov, uranu | 76 | Uranus Facts > Introduction | 11.057 |
| paráfrasis | Who first spotted the seventh planet? | first, spot, seventh, planet | 302 | About the Planets > Saturn's Hexagon / Mercury Facts / Venus Facts / Earth Facts / Mars Facts / Jupiter Facts / Saturn Facts / Uranus Facts / Neptune Facts | 22.419 |
| literal | What is the largest volcano in the solar system? | largest, volcano, solar, system | 253 | Mars Facts > The Largest Volcano | 19.537 |
| errores de escritura | What is the largset volcanno in the solar systme? | largset, volcanno, solar, systm | 198 | Sun Facts > Magnetosphere | 1.480 |
| literal | What is the smallest planet in our solar system? | smallest, planet, solar, system | 347 | About the Planets > Saturn's Hexagon / Mercury Facts / Venus Facts / Earth Facts / Mars Facts / Jupiter Facts / Saturn Facts / Uranus Facts / Neptune Facts | 20.723 |
| sinónimos | Which world is the tiniest in our planetary system? | world, tiniest, planetari, system | 228 | Solar System Facts > Namesake / Potential for Life | 12.593 |
