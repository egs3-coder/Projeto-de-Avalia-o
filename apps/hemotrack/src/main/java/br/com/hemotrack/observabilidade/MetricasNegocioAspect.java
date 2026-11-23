package br.com.hemotrack.observabilidade;

import br.com.hemotrack.excecao.RegraNegocioException;
import br.com.hemotrack.model.Bolsa;
import br.com.hemotrack.model.LeituraTemperatura;
import br.com.hemotrack.model.Requisicao;
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.AfterReturning;
import org.aspectj.lang.annotation.AfterThrowing;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

/**
 * Instrumentacao do HemoTrack sem alterar as regras de negocio:
 *
 * 1) Cria um span para cada metodo publico dos servicos (camada de servico no trace:
 *    HTTP -> RequisicaoService#criar -> consultas JDBC).
 *
 * 2) Metricas de negocio (ponto adicional), expostas em /actuator/prometheus:
 *    - hemotrack_requisicoes_criadas_total{urgencia}         Counter
 *    - hemotrack_requisicoes_recusadas_total                 Counter
 *    - hemotrack_bolsas_cadastradas_total{tipo_sanguineo}    Counter
 *    - hemotrack_telemetria_leituras_total{faixa}            Counter
 *    - hemotrack_logins_total{resultado}                     Counter
 *    - hemotrack_alocacao_tempo_seconds_*{resultado}         Timer
 *    (os Gauges de estoque ficam em MetricasEstoque)
 */
@Aspect
@Component
public class MetricasNegocioAspect {

    private static final Logger LOG = LoggerFactory.getLogger(MetricasNegocioAspect.class);

    private final MeterRegistry registry;
    private final ObservationRegistry observationRegistry;
    private final Counter requisicoesRecusadas;
    private final Counter loginsSucesso;
    private final Counter loginsFalha;

    public MetricasNegocioAspect(MeterRegistry registry, ObservationRegistry observationRegistry) {
        this.registry = registry;
        this.observationRegistry = observationRegistry;
        this.requisicoesRecusadas = Counter.builder("hemotrack.requisicoes.recusadas")
                .description("Requisicoes de hemocomponentes recusadas pela validacao (dados invalidos)")
                .register(registry);
        this.loginsSucesso = Counter.builder("hemotrack.logins")
                .description("Tentativas de entrada na plataforma, por resultado")
                .tag("resultado", "sucesso")
                .register(registry);
        this.loginsFalha = Counter.builder("hemotrack.logins")
                .description("Tentativas de entrada na plataforma, por resultado")
                .tag("resultado", "falha")
                .register(registry);
    }

    // ------------------------------------------------------------------ spans da camada de servico

    @Around("execution(public * br.com.hemotrack.service..*(..))")
    public Object observarServico(ProceedingJoinPoint ponto) throws Throwable {
        String classe = ponto.getSignature().getDeclaringType().getSimpleName();
        String metodo = ponto.getSignature().getName();
        Observation observacao = Observation.createNotStarted("hemotrack.servico", observationRegistry)
                .contextualName(classe + "#" + metodo)
                .lowCardinalityKeyValue("classe", classe)
                .lowCardinalityKeyValue("metodo", metodo)
                .start();
        try (Observation.Scope escopo = observacao.openScope()) {
            return ponto.proceed();
        } catch (Throwable erro) {
            observacao.error(erro);
            throw erro;
        } finally {
            observacao.stop();
        }
    }

    // ------------------------------------------------------------------ requisicoes (US01)

    @AfterReturning(pointcut = "execution(* br.com.hemotrack.service.RequisicaoService.criar(..))",
            returning = "requisicao")
    public void requisicaoCriada(Requisicao requisicao) {
        Counter.builder("hemotrack.requisicoes.criadas")
                .description("Requisicoes de hemocomponentes criadas, por urgencia")
                .tag("urgencia", requisicao.getUrgencia().name())
                .register(registry)
                .increment();
        LOG.info("Requisicao {} criada: hospital={}, {} x {} ({}), urgencia={}", requisicao.getCodigo(),
                requisicao.getHospital().getNome(), requisicao.getQuantidade(), requisicao.getHemocomponente().name(),
                requisicao.getTipoSanguineo().name(), requisicao.getUrgencia().name());
    }

    @AfterThrowing(pointcut = "execution(* br.com.hemotrack.service.RequisicaoService.criar(..))",
            throwing = "erro")
    public void requisicaoRecusada(RegraNegocioException erro) {
        requisicoesRecusadas.increment();
        LOG.warn("Requisicao recusada: {}", erro.getMessage());
    }

    // ------------------------------------------------------------------ alocacao FEFO (US04)

    @Around("execution(* br.com.hemotrack.service.RequisicaoService.alocar(..))")
    public Object medirAlocacao(ProceedingJoinPoint ponto) throws Throwable {
        Timer.Sample amostra = Timer.start(registry);
        String resultado = "alocada";
        try {
            Object retorno = ponto.proceed();
            LOG.info("Requisicao id={} alocada (bolsas reservadas por FEFO)", ponto.getArgs()[0]);
            return retorno;
        } catch (RegraNegocioException erro) {
            resultado = "sem_estoque_ou_invalida";
            LOG.warn("Alocacao da requisicao id={} nao realizada: {}", ponto.getArgs()[0], erro.getMessage());
            throw erro;
        } finally {
            amostra.stop(Timer.builder("hemotrack.alocacao.tempo")
                    .description("Tempo para alocar bolsas compativeis a uma requisicao (FEFO)")
                    .tag("resultado", resultado)
                    .register(registry));
        }
    }

    // ------------------------------------------------------------------ estoque (US03)

    @AfterReturning(pointcut = "execution(* br.com.hemotrack.service.BolsaService.cadastrar(..))",
            returning = "bolsa")
    public void bolsaCadastrada(Bolsa bolsa) {
        Counter.builder("hemotrack.bolsas.cadastradas")
                .description("Bolsas de sangue que deram entrada no estoque, por tipo sanguineo")
                .tag("tipo_sanguineo", bolsa.getTipoSanguineo().name())
                .register(registry)
                .increment();
        LOG.info("Bolsa {} ({}) adicionada ao estoque, validade {}", bolsa.getCodigo(),
                bolsa.getTipoSanguineo().name(), bolsa.getDataValidade());
    }

    // ------------------------------------------------------------------ telemetria (US06)

    @AfterReturning(pointcut = "execution(* br.com.hemotrack.service.TelemetriaService.registrar(..))",
            returning = "leitura")
    public void leituraRegistrada(LeituraTemperatura leitura) {
        String faixa = leitura.isForaDaFaixa() ? "fora" : "normal";
        Counter.builder("hemotrack.telemetria.leituras")
                .description("Leituras de temperatura recebidas do sensor, por faixa (normal ou fora da faixa segura)")
                .tag("faixa", faixa)
                .register(registry)
                .increment();
        if (leitura.isForaDaFaixa()) {
            LOG.warn("Temperatura FORA da faixa segura: {} C", leitura.getTemperatura());
        } else {
            LOG.info("Leitura de temperatura registrada: {} C", leitura.getTemperatura());
        }
    }

    // ------------------------------------------------------------------ acesso (US02)

    @AfterReturning("execution(* br.com.hemotrack.service.AutenticacaoService.autenticar(..))")
    public void loginComSucesso() {
        loginsSucesso.increment();
    }

    @AfterThrowing(pointcut = "execution(* br.com.hemotrack.service.AutenticacaoService.autenticar(..))",
            throwing = "erro")
    public void loginComFalha(RegraNegocioException erro) {
        loginsFalha.increment();
        LOG.warn("Falha de autenticacao: {}", erro.getMessage());
    }
}
